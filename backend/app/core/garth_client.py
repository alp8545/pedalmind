"""Garmin Connect client using garth (email/password auth).

Uses garth library for simpler auth flow — no OAuth setup required.
Tokens can be injected via GARTH_TOKENS env var (base64-encoded bundle)
for environments like Railway where filesystem state is ephemeral.
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

RATE_LIMIT_WAIT = 30  # seconds to wait on 429
MIN_CALL_INTERVAL = 2.0  # seconds between Garmin API calls

# Async rate limiter: serializes all Garmin API calls with a 2s floor
_rate_semaphore = asyncio.Semaphore(1)
_last_call_time = 0.0

_TOKEN_DIR = Path("/tmp/garth_tokens")
_bootstrap_log: list[str] = []  # debug breadcrumbs for /garmin/debug endpoint
_auth_failure_until: float = 0  # epoch timestamp — skip auth attempts until this time
_auth_failure_count: int = 0  # consecutive auth failures — longer backoff after repeated failures
_AUTH_BACKOFF_BASE = 300  # 5 min base backoff
_AUTH_BACKOFF_MAX = 3600  # 1 hour max backoff
_REFRESH_BUFFER_SECS = 300  # refresh 5 minutes BEFORE expiry to avoid last-second failures
_client_ready: bool = False  # True when we have a working session, skip re-auth


def _decode_garth_tokens() -> bool:
    """Decode GARTH_TOKENS env var (base64 JSON bundle) to disk. Returns True if files were written."""
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


API_TEST_URL = "/activitylist-service/activities/search/activities"


def _get_http_status(exc: Exception) -> int | None:
    """Extract HTTP status code from a GarthHTTPError, or None."""
    if isinstance(exc, GarthHTTPError):
        response = getattr(exc.error, "response", None)
        if response is not None:
            return response.status_code
    return None


def _test_api_call() -> tuple[str, dict | list | None, Exception | None]:
    """Make a lightweight API call to verify the session works.

    Returns (status, result, exception):
      - ("ok", data, None) on success
      - ("401", None, exc) on auth failure — caller should try refresh
      - ("error", None, exc) on other failures (404, 429, etc) — no refresh needed
    """
    try:
        result = garth.connectapi(API_TEST_URL, params={"limit": 1})
        return ("ok", result, None)
    except Exception as e:
        status_code = _get_http_status(e)
        if status_code == 401:
            return ("401", None, e)
        return ("error", None, e)


def _engage_backoff(reason: str):
    """Set auth backoff with exponential increase on repeated failures."""
    global _auth_failure_until, _auth_failure_count
    _auth_failure_count += 1
    backoff = min(_AUTH_BACKOFF_BASE * (2 ** (_auth_failure_count - 1)), _AUTH_BACKOFF_MAX)
    _auth_failure_until = time.time() + backoff
    _bootstrap_log.append(f"Auth backoff #{_auth_failure_count}: {backoff}s. Reason: {reason}")


def _needs_refresh() -> bool:
    """Check if the access token needs refreshing (expired or about to expire)."""
    if not hasattr(garth.client, "oauth2_token") or garth.client.oauth2_token is None:
        return True
    expires_at = garth.client.oauth2_token.expires_at
    return expires_at < (time.time() + _REFRESH_BUFFER_SECS)


def get_garth_client():
    """Login to Garmin Connect via garth, reuse session if possible.

    Key design: avoid the 429 spiral.
    1. If we already have a working session (_client_ready), reuse it. Only refresh
       if the token is about to expire (5 min buffer).
    2. On auth failure, use exponential backoff (5min → 10min → 20min → ... → 1hr max).
    3. NEVER attempt fresh login as fallback to a 429'd refresh. That just 429s a
       second endpoint. Only do fresh login when there are no tokens at all.
    4. Reset backoff on ANY successful auth.
    """
    global _auth_failure_until, _auth_failure_count, _client_ready

    # Fast path: session already working and token not about to expire
    if _client_ready and not _needs_refresh():
        return garth

    # If we recently failed auth, don't hammer Garmin again
    if _auth_failure_until > time.time():
        wait = int(_auth_failure_until - time.time())
        raise RuntimeError(
            f"Garmin auth is in backoff mode (retry in {wait}s). "
            f"Failure #{_auth_failure_count}. Next attempt at backoff expiry."
        )

    # Decode GARTH_TOKENS env var to disk on first run
    if not _TOKEN_DIR.exists():
        _decode_garth_tokens()

    # Try resume from token dir
    if _TOKEN_DIR.exists():
        try:
            garth.resume(str(_TOKEN_DIR))
            _bootstrap_log.append(f"Resumed garth session from {_TOKEN_DIR}")
        except Exception as e:
            _bootstrap_log.append(f"Resume failed from {_TOKEN_DIR}: {e}")
            # Fall through to fresh login below

        # Check if token needs refresh
        if _needs_refresh():
            _bootstrap_log.append(
                f"Access token needs refresh (expires_at={garth.client.oauth2_token.expires_at})"
            )
            try:
                garth.client.refresh_oauth2()
                garth.save(str(_TOKEN_DIR))
                _auth_failure_count = 0  # Reset on success
                _client_ready = True
                _bootstrap_log.append("Token refresh succeeded, saved to disk")
                return garth
            except Exception as refresh_err:
                _bootstrap_log.append(f"Token refresh failed: {refresh_err}")
                # DO NOT try fresh login here — that just 429s a second endpoint.
                # Instead, check if the old access token might still work (Garmin
                # sometimes accepts tokens slightly past expiry).
                test_status, _, _ = _test_api_call()
                if test_status == "ok":
                    _bootstrap_log.append("Old access token still works despite refresh failure")
                    _client_ready = True
                    return garth
                # Both refresh and API failed — engage backoff
                _engage_backoff(f"refresh failed: {refresh_err}")
                raise RuntimeError(f"Token refresh failed: {refresh_err}")
        else:
            _bootstrap_log.append(
                f"Access token still valid (expires_at={garth.client.oauth2_token.expires_at})"
            )
            _client_ready = True
            return garth

    # No tokens on disk — fresh login is the only option
    if not settings.GARMIN_EMAIL or not settings.GARMIN_PASSWORD:
        raise RuntimeError(
            "Cannot authenticate to Garmin: no GARTH_TOKENS, no saved tokens, "
            "and GARMIN_EMAIL/GARMIN_PASSWORD not set"
        )
    _bootstrap_log.append("No tokens found, attempting fresh login...")
    try:
        garth.login(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)
        _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        garth.save(str(_TOKEN_DIR))
        _auth_failure_count = 0
        _client_ready = True
        _bootstrap_log.append("Fresh login successful, tokens saved")
        return garth
    except Exception as login_err:
        _engage_backoff(f"fresh login failed: {login_err}")
        raise RuntimeError(f"Fresh login failed: {login_err}")


def get_bootstrap_debug() -> dict:
    """Return debug info about garth token bootstrap for the /garmin/debug endpoint."""
    token_dir_exists = _TOKEN_DIR.exists()
    token_files = sorted(f.name for f in _TOKEN_DIR.iterdir()) if token_dir_exists else []

    # Token details
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
                    "scope_preview": str(t.get("scope", ""))[:80] + "...",
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
        "bootstrap_log": list(_bootstrap_log),
    }


def reset_auth_backoff():
    """Manually reset the auth backoff state. Use after Garmin rate limit clears."""
    global _auth_failure_until, _auth_failure_count, _client_ready
    _auth_failure_until = 0
    _auth_failure_count = 0
    _client_ready = False
    _bootstrap_log.append("Auth backoff manually reset")


class GarminRateLimitError(Exception):
    """Raised when Garmin returns 429 even after retry."""
    pass


def _is_rate_limit(exc: Exception) -> bool:
    """Check if an exception is a 429 rate-limit error."""
    if isinstance(exc, GarthHTTPError):
        response = getattr(exc.error, "response", None)
        if response is not None and response.status_code == 429:
            return True
    return "429" in str(exc)


def _call_with_retry(func, *args, **kwargs):
    """Call a garth API function with rate limiting and exponential backoff.

    Rate limit: enforces MIN_CALL_INTERVAL between calls.
    Retry: on 429 or timeout, retries up to 3 attempts total with 30s/60s waits.
    """
    global _last_call_time
    backoff_schedule = [30, 60]  # seconds to wait after 1st and 2nd failures

    for attempt in range(3):
        # Enforce minimum interval between calls
        elapsed = time.time() - _last_call_time
        if elapsed < MIN_CALL_INTERVAL:
            delay = MIN_CALL_INTERVAL - elapsed
            logger.debug("Rate limit: sleeping %.1fs before Garmin API call", delay)
            time.sleep(delay)

        try:
            _last_call_time = time.time()
            return func(*args, **kwargs)
        except requests.exceptions.Timeout as e:
            if attempt < 2:
                wait = backoff_schedule[attempt]
                logger.warning("Garmin timeout (attempt %d/3), waiting %ds", attempt + 1, wait)
                time.sleep(wait)
            else:
                raise GarminRateLimitError("Garmin timeout after 3 attempts") from e
        except Exception as e:
            if not _is_rate_limit(e):
                raise
            if attempt < 2:
                wait = backoff_schedule[attempt]
                logger.warning("Garmin 429 (attempt %d/3), waiting %ds", attempt + 1, wait)
                time.sleep(wait)
            else:
                raise GarminRateLimitError("Garmin rate limit (429) after 3 attempts") from e


async def rate_limited_call(func, *args, **kwargs):
    """Async wrapper that serializes Garmin API calls through a semaphore.

    Use this from async endpoints instead of calling _call_with_retry directly.
    Keeps the event loop free while waiting for the rate limit interval.
    """
    async with _rate_semaphore:
        global _last_call_time
        elapsed = time.time() - _last_call_time
        if elapsed < MIN_CALL_INTERVAL:
            await asyncio.sleep(MIN_CALL_INTERVAL - elapsed)
        return await asyncio.to_thread(_call_with_retry, func, *args, **kwargs)


def fetch_activities(days: int = 3, limit: int = 50) -> list[dict]:
    """Fetch activity list from the last N days."""
    client = get_garth_client()

    activities = _call_with_retry(
        client.connectapi,
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


def fetch_activity_details(activity_id: int) -> dict:
    """Fetch full details for a single activity."""
    client = get_garth_client()

    details = _call_with_retry(
        client.connectapi, f"/activity-service/activity/{activity_id}"
    )

    # Splits / laps
    try:
        splits = _call_with_retry(
            client.connectapi,
            f"/activity-service/activity/{activity_id}/splits",
        )
        details["splits"] = splits
    except Exception:
        details["splits"] = None

    # HR time in zones
    try:
        hr_zones = _call_with_retry(
            client.connectapi,
            f"/activity-service/activity/{activity_id}/hrTimeInZones",
        )
        details["hrTimeInZones"] = hr_zones
    except Exception:
        details["hrTimeInZones"] = None

    # Power time in zones
    try:
        power_zones = _call_with_retry(
            client.connectapi,
            f"/activity-service/activity/{activity_id}/powerTimeInZones",
        )
        details["powerTimeInZones"] = power_zones
    except Exception:
        details["powerTimeInZones"] = None

    return details
