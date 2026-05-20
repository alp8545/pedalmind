"""Garmin Connect client using garth (email/password auth).

All Garmin API calls are serialized through a single asyncio.Lock to prevent:
- Race conditions on the garth global singleton
- Concurrent auth refresh attempts
- Rate limit violations from parallel requests

Every call goes through `garmin_api_call()` which handles auth, rate limiting,
retries, and event loop safety (asyncio.to_thread for all blocking calls).
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
_AUTH_BACKOFF_BASE = 60   # 1 min base backoff (Render cold-start friendly)
_AUTH_BACKOFF_MAX = 600   # 10 min max backoff
_REFRESH_BUFFER_SECS = 300  # refresh 5 min BEFORE expiry

# ---- State (protected by _garmin_lock) ----
_garmin_lock = asyncio.Lock()  # serializes ALL Garmin operations
_last_call_time = 0.0
_client_ready: bool = False
_auth_failure_until: float = 0
_auth_failure_count: int = 0

_TOKEN_DIR = Path("/tmp/garth_tokens")
_bootstrap_log: list[str] = []


class GarminRateLimitError(Exception):
    """Raised when Garmin returns 429 even after retry."""
    pass


# ---- Token management (all synchronous, called from within asyncio.to_thread) ----

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
        return True  # BUG-3 fix: handle None expires_at
    return expires_at < (time.time() + _REFRESH_BUFFER_SECS)


def _engage_backoff(reason: str):
    """Set auth backoff with exponential increase on repeated failures."""
    global _auth_failure_until, _auth_failure_count
    _auth_failure_count += 1
    backoff = min(_AUTH_BACKOFF_BASE * (2 ** (_auth_failure_count - 1)), _AUTH_BACKOFF_MAX)
    _auth_failure_until = time.time() + backoff
    _bootstrap_log.append(f"Auth backoff #{_auth_failure_count}: {backoff}s. Reason: {reason}")


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


def _try_fresh_login() -> bool:
    """Attempt fresh login with email/password. Returns True on success."""
    global _auth_failure_count, _client_ready
    if not settings.GARMIN_EMAIL or not settings.GARMIN_PASSWORD:
        _bootstrap_log.append("No GARMIN_EMAIL/PASSWORD for fresh login")
        return False
    _bootstrap_log.append("Attempting fresh login...")
    try:
        garth.login(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)
        _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        garth.save(str(_TOKEN_DIR))
        _auth_failure_count = 0
        _client_ready = True
        _bootstrap_log.append("Fresh login successful")
        return True
    except Exception as login_err:
        _bootstrap_log.append(f"Fresh login failed: {login_err}")
        return False


def _ensure_auth():
    """Ensure garth has a valid session. Called synchronously from thread pool.

    Handles token decode, resume, refresh, and fresh login fallback.
    Auth flow: resume saved tokens -> refresh via OAuth1 -> fresh login.
    Only falls back to fresh login when refresh fails with non-429 error
    (rate-limited refresh should wait, not escalate to sso.garmin.com).
    """
    global _auth_failure_until, _auth_failure_count, _client_ready

    # Fast path: session already working and token not about to expire
    if _client_ready and not _needs_refresh():
        return

    # Backoff check
    if _auth_failure_until > time.time():
        wait = int(_auth_failure_until - time.time())
        raise RuntimeError(
            f"Garmin auth in backoff mode (retry in {wait}s). Failure #{_auth_failure_count}."
        )

    # Decode GARTH_TOKENS env var to disk on first run, or if dir is empty
    if not _TOKEN_DIR.exists() or not any(_TOKEN_DIR.iterdir()):
        _decode_garth_tokens()

    # Try resume from token dir
    if _TOKEN_DIR.exists() and any(_TOKEN_DIR.iterdir()):
        resumed_ok = False
        try:
            garth.resume(str(_TOKEN_DIR))
            resumed_ok = True
            _bootstrap_log.append(f"Resumed garth session from {_TOKEN_DIR}")
        except Exception as e:
            _bootstrap_log.append(f"Resume failed: {e}")
            # Tokens unreadable — clear them so the next step tries env var / fresh login
            for f in _TOKEN_DIR.iterdir():
                f.unlink()

        if resumed_ok:
            if _needs_refresh():
                _bootstrap_log.append("Access token needs refresh")
                try:
                    garth.client.refresh_oauth2()
                    garth.save(str(_TOKEN_DIR))
                    _auth_failure_count = 0
                    _client_ready = True
                    _bootstrap_log.append("Token refresh succeeded")
                    return
                except Exception as refresh_err:
                    _bootstrap_log.append(f"Token refresh failed: {refresh_err}")
                    # Connectapi.garmin.com has a wider grace period than nominal —
                    # the old access token may still work even after refresh fails.
                    try:
                        garth.connectapi(
                            "/activitylist-service/activities/search/activities",
                            params={"limit": 1},
                        )
                        _bootstrap_log.append("Old access token still works despite refresh failure")
                        _client_ready = True
                        return
                    except Exception:
                        pass

                    # On 429: preserve tokens. The next backoff cycle will retry refresh —
                    # sso.garmin.com fresh-login shares the same account-level rate limit,
                    # so trying it now just compounds the 429. Engage backoff and bail.
                    if _is_rate_limit(refresh_err):
                        _bootstrap_log.append("Refresh rate-limited (429) — preserving tokens, engaging backoff")
                        _engage_backoff("refresh rate-limited (429)")
                        raise RuntimeError(
                            f"Garmin refresh rate-limited. Tokens preserved for retry. "
                            f"Auth backoff #{_auth_failure_count}."
                        )

                    # On 401/403 (truly invalid) or other errors: clear and fall through to fresh login
                    _bootstrap_log.append("OAuth1 token appears invalid, clearing stale tokens")
                    for f in _TOKEN_DIR.iterdir():
                        f.unlink()
            else:
                _client_ready = True
                return

    # No valid tokens — fresh login as last resort
    if _try_fresh_login():
        return

    _engage_backoff("all auth methods failed")
    raise RuntimeError(
        "Garmin auth failed: token refresh failed and fresh login failed. "
        "Inject fresh tokens via POST /garmin/auth/inject-tokens"
    )


def _sync_api_call(endpoint: str, method: str = "GET", **kwargs):
    """Synchronous Garmin API call with rate limiting and retry.

    Called from within asyncio.to_thread, so time.sleep is safe here.
    """
    global _last_call_time
    backoff_schedule = [30, 60]

    _ensure_auth()

    for attempt in range(3):
        # Enforce minimum interval between calls
        elapsed = time.time() - _last_call_time
        if elapsed < MIN_CALL_INTERVAL:
            delay = MIN_CALL_INTERVAL - elapsed
            time.sleep(delay)

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
            # BUG-6 fix: catch ConnectionError, not just Timeout
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

    Serializes through _garmin_lock (prevents race conditions on garth singleton),
    runs in thread pool (prevents event loop blocking), handles auth + rate limiting.
    """
    async with _garmin_lock:  # BUG-1 fix: one lock for everything
        return await asyncio.to_thread(_sync_api_call, endpoint, method, **kwargs)


async def proactive_token_refresh():
    """Attempt token refresh on startup. Non-fatal: logs but doesn't crash the app.

    Restores tokens from DB → /tmp before refreshing, and persists back to
    DB after a successful refresh so the next container restart has fresh tokens.
    """
    from app.core.token_store import load_tokens_from_db_to_disk, save_disk_tokens_to_db

    # Step 1 — restore from DB if /tmp is empty (e.g., fresh container)
    if not _TOKEN_DIR.exists() or not any(_TOKEN_DIR.iterdir()):
        await load_tokens_from_db_to_disk()

    try:
        async with _garmin_lock:
            await asyncio.to_thread(_ensure_auth)
        logger.info("Proactive token refresh succeeded, client ready")
        # Step 2 — persist (potentially refreshed) tokens to DB
        await save_disk_tokens_to_db()
    except Exception as e:
        logger.warning("Proactive token refresh failed (non-fatal): %s", e)


async def periodic_token_refresh(interval_seconds: int = 30 * 60):
    """Background loop that refreshes the oauth2 token periodically.

    Default cadence: every 30 min. Each iteration calls _ensure_auth (which is
    a no-op if the access token still has more than 5 min left) and persists
    the bundle to the DB. Cadence chosen to be well below the ~1h access-token
    TTL so the loop catches expiry even when the container is briefly slow,
    yet far above Garmin's per-call rate-limit threshold.

    Note: on Render free the container sleeps after 15 min idle, so this loop
    alone is not enough — it must be paired with the external GitHub Actions
    cron hitting /api/garmin/auth/keep-warm to guarantee freshness when the
    user has not opened the app for days.
    """
    from app.core.token_store import save_disk_tokens_to_db, days_until_refresh_expires

    # Wait a minute after boot to avoid competing with the startup refresh
    await asyncio.sleep(60)
    while True:
        try:
            async with _garmin_lock:
                await asyncio.to_thread(_ensure_auth)
            await save_disk_tokens_to_db()
            days_left = days_until_refresh_expires()
            if days_left is not None and days_left < 7:
                logger.warning(
                    "Garmin refresh-token expires in %.1f days — manual re-login soon required",
                    days_left,
                )
            else:
                logger.info("Periodic Garmin refresh OK (refresh-token: %.1f days left)",
                            days_left if days_left is not None else -1)
        except Exception as e:
            logger.warning("Periodic Garmin refresh failed (non-fatal): %s", e)
        await asyncio.sleep(interval_seconds)


# ---- High-level helpers (all async, all go through garmin_api_call) ----

async def async_fetch_activities(days: int = 3, limit: int = 50) -> list[dict]:
    """Fetch activity list from the last N days."""
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
    """Fetch full details for a single activity (details + splits + zones)."""
    details = await garmin_api_call(f"/activity-service/activity/{activity_id}")

    # Secondary data — failures are non-fatal (BUG-7: log instead of silently swallow)
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
    """Get a garminconnect.Garmin client backed by the current garth session."""
    from garminconnect import Garmin
    _ensure_auth()
    client = Garmin()
    client.garth = garth.client
    return client


async def async_upload_workout(workout_dict: dict) -> dict:
    """Upload a workout to Garmin Connect."""
    async with _garmin_lock:
        def _upload():
            client = _get_garmin_connect_client()
            return client.upload_workout(workout_dict)
        return await asyncio.to_thread(_upload)


async def async_schedule_workout(workout_id: str, date_str: str):
    """Schedule a workout on Garmin Connect."""
    async with _garmin_lock:
        def _schedule():
            client = _get_garmin_connect_client()
            client.schedule_workout(workout_id, date_str)
        return await asyncio.to_thread(_schedule)


# ---- Sync wrappers (for backward compat, used by garmin_sync.py via asyncio.to_thread) ----
# These are DEPRECATED — callers should migrate to async_* versions above

def fetch_activities(days: int = 3, limit: int = 50) -> list[dict]:
    """DEPRECATED: Use async_fetch_activities instead."""
    client = get_garth_client()
    return _sync_api_call(
        "/activitylist-service/activities/search/activities",
        params={
            "start": 0,
            "limit": limit,
            "startDate": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "endDate": datetime.now().strftime("%Y-%m-%d"),
        },
    )


def fetch_activity_details(activity_id: int) -> dict:
    """DEPRECATED: Use async_fetch_activity_details instead."""
    return _sync_api_call(f"/activity-service/activity/{activity_id}")


def get_garth_client():
    """DEPRECATED: Auth is now handled internally. Returns garth module."""
    _ensure_auth()
    return garth


# ---- Debug and admin ----

API_TEST_URL = "/activitylist-service/activities/search/activities"


def get_bootstrap_debug() -> dict:
    """Return debug info about garth token bootstrap (full — includes access-token preview)."""
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
        "auth_failure_count": _auth_failure_count,
        "auth_backoff_remaining": max(0, int(_auth_failure_until - time.time())),
        "client_ready": _client_ready,
        "bootstrap_log": list(_bootstrap_log),
    }


def get_public_debug() -> dict:
    """Sanitized debug info safe to expose without JWT auth.

    No token previews, no env-var lengths — just timing/state so a cron or curl
    can verify token freshness from outside.
    """
    now = int(time.time())
    access_secs_left = None
    refresh_days_left = None
    refresh_token_expired = None

    try:
        oauth2_path = _TOKEN_DIR / "oauth2_token.json"
        if oauth2_path.exists():
            t = json.loads(oauth2_path.read_text())
            exp = int(t.get("expires_at") or 0)
            rexp = int(t.get("refresh_token_expires_at") or 0)
            if exp:
                access_secs_left = exp - now
            if rexp:
                refresh_days_left = round((rexp - now) / 86400.0, 2)
                refresh_token_expired = rexp < now
    except Exception:
        pass

    return {
        "client_ready": _client_ready,
        "token_dir_present": _TOKEN_DIR.exists() and any(_TOKEN_DIR.iterdir()),
        "access_token_seconds_left": access_secs_left,
        "refresh_token_days_left": refresh_days_left,
        "refresh_token_expired": refresh_token_expired,
        "auth_failure_count": _auth_failure_count,
        "auth_backoff_remaining": max(0, int(_auth_failure_until - now)),
        # Last 10 log lines so we can see recent state without leaking history
        "bootstrap_log_tail": list(_bootstrap_log[-10:]),
    }


def reset_auth_backoff():
    """Manually reset the auth backoff state."""
    global _auth_failure_until, _auth_failure_count, _client_ready
    _auth_failure_until = 0
    _auth_failure_count = 0
    _client_ready = False
    _bootstrap_log.append("Auth backoff manually reset")
