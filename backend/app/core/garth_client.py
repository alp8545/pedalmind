"""Garmin Connect client using garth (email/password auth).

All Garmin API calls are serialized through a single asyncio.Lock to prevent:
- Race conditions on the garth global singleton
- Concurrent auth refresh attempts
- Rate limit violations from parallel requests

Every call goes through `garmin_api_call()` which:
1. Calls `ensure_auth_async()` to make sure tokens are fresh
2. Holds `_garmin_lock` while invoking garth.connectapi in a thread

OAuth refresh state (failure count, backoff window, in-flight flag) lives in
the DB via `token_store.attempt_refresh()`. Module-level globals MUST NOT
carry refresh state — Render free wipes them on every cold-start, which would
trigger immediate retries and reset Garmin's account-level 429 timer.
"""

import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import garth
import requests.exceptions
from garth.exc import GarthHTTPError

from app.core.config import settings

logger = logging.getLogger("garth_client")

# ---- Configuration ----
MIN_CALL_INTERVAL = 2.0  # seconds between Garmin API calls
_REFRESH_BUFFER_SECS = 600  # refresh 10 min BEFORE expiry (bigger margin = less thrash)

# ---- State (only what's safe to keep in-memory: the API call lock and timing) ----
_garmin_lock = asyncio.Lock()  # serializes ALL Garmin operations
_last_call_time = 0.0
_client_ready: bool = False  # local "garth.resume() has been called" cache

_TOKEN_DIR = Path("/tmp/garth_tokens")
_bootstrap_log: list[str] = []


class GarminRateLimitError(Exception):
    """Raised when Garmin returns 429 even after retry."""
    pass


class GarminInBackoffError(Exception):
    """Raised when Garmin auth is in persistent backoff and the access token cannot be used.

    retry_after_seconds tells the caller (and the user via Retry-After header)
    how long to wait. This is account-level and IP rotation does not help.
    """

    def __init__(self, retry_after_seconds: int, message: str | None = None):
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        super().__init__(message or f"Garmin auth in backoff for {self.retry_after_seconds}s")


# ---- Token helpers (synchronous, called from within asyncio.to_thread) ----

def _decode_garth_tokens() -> bool:
    """Decode GARTH_TOKENS env var (base64 JSON bundle) to disk."""
    garth_b64 = os.environ.get("GARTH_TOKENS", "")
    if not garth_b64:
        _bootstrap_log.append("GARTH_TOKENS env var not set")
        return False
    try:
        bundle = json.loads(base64.b64decode(garth_b64))
        _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        written = []
        for fname, content in bundle.items():
            fpath = _TOKEN_DIR / fname
            fpath.write_text(json.dumps(content))
            written.append(fname)
        _bootstrap_log.append(f"Decoded GARTH_TOKENS -> wrote {written} to {_TOKEN_DIR}")
        return True
    except Exception as e:
        _bootstrap_log.append(f"Failed to decode GARTH_TOKENS: {e}")
        return False


def _needs_refresh() -> bool:
    """Check if the access token needs refreshing (expired or about to expire)."""
    if not hasattr(garth.client, "oauth2_token") or garth.client.oauth2_token is None:
        return True
    expires_at = garth.client.oauth2_token.expires_at
    if expires_at is None:
        return True
    return expires_at < (time.time() + _REFRESH_BUFFER_SECS)


def _is_rate_limit(exc: Exception) -> bool:
    """Check if an exception is a 429 rate-limit error."""
    if isinstance(exc, GarthHTTPError):
        response = getattr(exc.error, "response", None)
        if response is not None and response.status_code == 429:
            return True
    return "429" in str(exc)


def _is_token_invalid(exc: Exception) -> bool:
    """Check if an exception means the token is permanently invalid (401/403)."""
    if isinstance(exc, GarthHTTPError):
        response = getattr(exc.error, "response", None)
        if response is not None and response.status_code in (401, 403):
            return True
    for code in ("401", "403", "Unauthorized", "Forbidden"):
        if code in str(exc):
            return True
    return False


def _try_resume_from_disk() -> bool:
    """Resume garth session from /tmp/garth_tokens. Returns True on success."""
    global _client_ready
    if not _TOKEN_DIR.exists() or not any(_TOKEN_DIR.iterdir()):
        _decode_garth_tokens()
    if not _TOKEN_DIR.exists() or not any(_TOKEN_DIR.iterdir()):
        return False
    try:
        garth.resume(str(_TOKEN_DIR))
        _client_ready = True
        _bootstrap_log.append(f"Resumed garth session from {_TOKEN_DIR}")
        return True
    except Exception as e:
        _bootstrap_log.append(f"Resume failed: {e}")
        return False


def _try_fresh_login() -> bool:
    """Attempt fresh login with email/password. Returns True on success.

    Called ONLY by token_store.attempt_refresh on 401/403 (token truly invalid).
    Never called on 429 — sso.garmin.com shares the account-level rate limit.
    """
    global _client_ready
    if not settings.GARMIN_EMAIL or not settings.GARMIN_PASSWORD:
        _bootstrap_log.append("No GARMIN_EMAIL/PASSWORD for fresh login")
        return False
    _bootstrap_log.append("Attempting fresh login...")
    try:
        garth.login(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)
        _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        garth.save(str(_TOKEN_DIR))
        _client_ready = True
        _bootstrap_log.append("Fresh login successful")
        return True
    except Exception as login_err:
        _bootstrap_log.append(f"Fresh login failed: {login_err}")
        return False


def _ensure_resumed_sync() -> bool:
    """Make sure garth.client has tokens loaded from disk. Does NOT refresh.

    Returns True if garth is now usable (has tokens), False otherwise.
    Safe to call from within asyncio.to_thread.
    """
    if _client_ready and hasattr(garth.client, "oauth2_token") and garth.client.oauth2_token is not None:
        return True
    return _try_resume_from_disk()


async def ensure_auth_async() -> None:
    """Async entry point: make sure garth has a fresh, usable access token.

    Strategy:
      1. Reload tokens from DB → disk so we see what (possibly another container)
         might have refreshed.
      2. Resume garth from disk.
      3. If access token still has >10 min left → done.
      4. Otherwise call the chokepoint `attempt_refresh()`:
         - If it refreshed: reload from disk and continue
         - If it skipped (backoff/in-flight): check if the existing access token
           is still good enough to attempt this call; if not, raise GarminInBackoffError.
    """
    # Always re-read from DB so we see refreshes done by another container/process
    from app.core.token_store import load_tokens_from_db_to_disk, attempt_refresh

    await load_tokens_from_db_to_disk()
    await asyncio.to_thread(_ensure_resumed_sync)

    if not _needs_refresh():
        return

    result = await attempt_refresh(force=False)
    if result.get("refreshed"):
        # Reload from disk + re-resume so garth's in-memory state matches
        await load_tokens_from_db_to_disk()
        await asyncio.to_thread(_try_resume_from_disk)
        return

    # Refresh was skipped or failed. Can we still use the current access token?
    if hasattr(garth.client, "oauth2_token") and garth.client.oauth2_token is not None:
        try:
            secs_left = int(garth.client.oauth2_token.expires_at - time.time())
        except Exception:
            secs_left = -1
        if secs_left > 60:
            # Still some life — try the call. Refresh will retry on the next request.
            logger.info("Refresh skipped (%s) but access token has %ds left — proceeding",
                        result.get("skip_reason"), secs_left)
            return

    # No usable access token → propagate a clear backoff signal
    retry_after = (
        result.get("retry_after_seconds")
        or result.get("auth_failure_until_in_seconds")
        or 1800
    )
    reason = result.get("skip_reason") or ("rate_limited" if result.get("rate_limited") else "auth_failed")
    raise GarminInBackoffError(retry_after, f"Garmin auth unavailable ({reason})")


def _sync_api_call(endpoint: str, method: str = "GET", **kwargs):
    """Synchronous Garmin API call with rate limiting and retry.

    Assumes auth has already been ensured by `ensure_auth_async()`.
    Called from within `_garmin_lock` + asyncio.to_thread.
    """
    global _last_call_time
    backoff_schedule = [30, 60]

    for attempt in range(3):
        elapsed = time.time() - _last_call_time
        if elapsed < MIN_CALL_INTERVAL:
            time.sleep(MIN_CALL_INTERVAL - elapsed)

        try:
            _last_call_time = time.time()
            if method == "GET":
                return garth.connectapi(endpoint, **kwargs)
            else:
                return garth.connectapi(endpoint, method=method, **kwargs)
        except requests.exceptions.Timeout as e:
            if attempt < 2:
                wait = backoff_schedule[attempt]
                logger.warning("Garmin timeout (attempt %d/3), waiting %ds", attempt + 1, wait)
                time.sleep(wait)
            else:
                raise GarminRateLimitError("Garmin timeout after 3 attempts") from e
        except requests.exceptions.ConnectionError as e:
            if attempt < 2:
                wait = backoff_schedule[attempt]
                logger.warning("Garmin connection error (attempt %d/3), waiting %ds", attempt + 1, wait)
                time.sleep(wait)
            else:
                raise GarminRateLimitError("Garmin connection failed after 3 attempts") from e
        except Exception as e:
            if not _is_rate_limit(e):
                raise
            if attempt < 2:
                wait = backoff_schedule[attempt]
                logger.warning("Garmin 429 (attempt %d/3), waiting %ds", attempt + 1, wait)
                time.sleep(wait)
            else:
                raise GarminRateLimitError("Garmin rate limit (429) after 3 attempts") from e


async def garmin_api_call(endpoint: str, method: str = "GET", **kwargs):
    """THE single entry point for all Garmin API calls.

    Order: ensure_auth (may attempt one refresh) → lock + to_thread → connectapi.
    """
    await ensure_auth_async()
    async with _garmin_lock:
        return await asyncio.to_thread(_sync_api_call, endpoint, method, **kwargs)


async def proactive_token_refresh() -> dict:
    """Startup hook: try a refresh via the chokepoint. Never blocks/raises.

    The chokepoint internally respects the persistent backoff so if we are
    still inside Garmin's account-level cooldown after a restart, this is a no-op.
    """
    from app.core.token_store import (
        load_tokens_from_db_to_disk, attempt_refresh,
    )
    try:
        await load_tokens_from_db_to_disk()
        await asyncio.to_thread(_ensure_resumed_sync)

        # Only attempt refresh if the on-disk token actually needs it
        if not _needs_refresh():
            logger.info("Proactive refresh: skipped (access token still fresh)")
            return {"refreshed": False, "reason": "still_fresh"}

        result = await attempt_refresh(force=False)
        if result.get("refreshed"):
            logger.info("Proactive refresh: succeeded")
        else:
            logger.info("Proactive refresh: skipped/failed (%s)", result.get("skip_reason") or result.get("error"))
        return result
    except Exception as e:
        logger.warning("Proactive refresh hit unexpected error: %s", e)
        return {"refreshed": False, "error": str(e)[:200]}


# ---- High-level helpers ----

async def async_fetch_activities(days: int = 3, limit: int = 50) -> list[dict]:
    activities = await garmin_api_call(
        "/activitylist-service/activities/search/activities",
        params={
            "start": 0,
            "limit": limit,
            "startDate": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "endDate": datetime.now().strftime("%Y-%m-%d"),
        },
    )
    logger.info("Fetched %d activities from last %d days", len(activities), days)
    return activities


async def async_fetch_activity_details(activity_id: int) -> dict:
    details = await garmin_api_call(f"/activity-service/activity/{activity_id}")
    for endpoint, key in [
        (f"/activity-service/activity/{activity_id}/splits", "splits"),
        (f"/activity-service/activity/{activity_id}/hrTimeInZones", "hrTimeInZones"),
        (f"/activity-service/activity/{activity_id}/powerTimeInZones", "powerTimeInZones"),
    ]:
        try:
            details[key] = await garmin_api_call(endpoint)
        except Exception as e:
            logger.warning("Failed to fetch %s for activity %s: %s", key, activity_id, e)
            details[key] = None
    return details


def _get_garmin_connect_client():
    """Get a garminconnect.Garmin client backed by the current garth session.

    Caller must have already awaited `ensure_auth_async()` before invoking this
    (since this runs inside asyncio.to_thread and cannot itself await).
    """
    from garminconnect import Garmin
    _ensure_resumed_sync()
    client = Garmin()
    client.garth = garth.client
    return client


async def async_upload_workout(workout_dict: dict) -> dict:
    await ensure_auth_async()
    async with _garmin_lock:
        def _upload():
            client = _get_garmin_connect_client()
            return client.upload_workout(workout_dict)
        return await asyncio.to_thread(_upload)


async def async_schedule_workout(workout_id: str, date_str: str):
    await ensure_auth_async()
    async with _garmin_lock:
        def _schedule():
            client = _get_garmin_connect_client()
            client.schedule_workout(workout_id, date_str)
        return await asyncio.to_thread(_schedule)


# ---- Debug and admin ----

API_TEST_URL = "/activitylist-service/activities/search/activities"


def get_bootstrap_debug() -> dict:
    """Debug info about garth token bootstrap (full — includes access-token preview)."""
    token_dir_exists = _TOKEN_DIR.exists()
    token_files = sorted(f.name for f in _TOKEN_DIR.iterdir()) if token_dir_exists else []

    token_details = {}
    if token_dir_exists:
        try:
            oauth2_path = _TOKEN_DIR / "oauth2_token.json"
            if oauth2_path.exists():
                t = json.loads(oauth2_path.read_text())
                token_details = {
                    "access_token_preview": str(t.get("access_token", ""))[:20] + "...",
                    "expires_at": t.get("expires_at"),
                    "expired": t.get("expires_at", 0) < time.time(),
                    "refresh_token_exists": bool(t.get("refresh_token")),
                    "refresh_token_expires_at": t.get("refresh_token_expires_at"),
                    "refresh_token_expired": t.get("refresh_token_expires_at", 0) < time.time(),
                }
        except Exception as e:
            token_details = {"error": str(e)}

    return {
        "garth_tokens_env_set": bool(os.environ.get("GARTH_TOKENS", "")),
        "garth_tokens_env_length": len(os.environ.get("GARTH_TOKENS", "")),
        "token_dir": str(_TOKEN_DIR),
        "token_dir_exists": token_dir_exists,
        "token_files": token_files,
        "token_details": token_details,
        "client_ready": _client_ready,
        "bootstrap_log": list(_bootstrap_log),
    }


async def get_public_debug() -> dict:
    """Sanitized debug info safe to expose without JWT auth.

    Reads the persistent backoff state from the DB so it survives container restarts.
    """
    from app.core.token_store import (
        get_refresh_state, auth_backoff_remaining_seconds,
        seconds_until_access_expires, days_until_refresh_expires,
        refresh_token_expires_at,
    )

    now = int(time.time())
    access_secs = seconds_until_access_expires()
    refresh_days = days_until_refresh_expires()
    rexp = refresh_token_expires_at()
    refresh_expired = (rexp is not None and rexp < now)

    state = await get_refresh_state()
    backoff_remaining = auth_backoff_remaining_seconds(state)

    def _iso(dt):
        return dt.isoformat() if dt else None

    return {
        "client_ready": _client_ready,
        "token_dir_present": _TOKEN_DIR.exists() and any(_TOKEN_DIR.iterdir()),
        "access_token_seconds_left": access_secs,
        "refresh_token_days_left": refresh_days,
        "refresh_token_expired": refresh_expired,
        "auth_failure_count": state["auth_failure_count"],
        "auth_backoff_remaining": backoff_remaining,
        "auth_backoff_until": _iso(state["auth_failure_until"]),
        "last_refresh_attempt_at": _iso(state["last_refresh_attempt_at"]),
        "last_refresh_success_at": _iso(state["last_refresh_success_at"]),
        "last_429_at": _iso(state["last_429_at"]),
        "refresh_in_flight": state["refresh_in_flight"],
        "last_error": state["last_error"],
        "bootstrap_log_tail": list(_bootstrap_log[-10:]),
    }


async def reset_auth_backoff(reason: str = "manual reset") -> None:
    """Clear the persistent backoff state + the in-memory ready flag."""
    global _client_ready
    from app.core.token_store import reset_backoff_state
    await reset_backoff_state(reason=reason)
    _client_ready = False
    _bootstrap_log.append(f"Auth backoff reset: {reason}")
