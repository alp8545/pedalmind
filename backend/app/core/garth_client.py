"""Garmin Connect client using garth (email/password auth).

Uses garth library for simpler auth flow — no OAuth setup required.
Tokens can be injected via GARTH_TOKENS env var (base64-encoded bundle)
for environments like Railway where filesystem state is ephemeral.
"""

import base64
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import garth
from garth.exc import GarthHTTPError

from app.core.config import settings

logger = logging.getLogger("garth_client")

RATE_LIMIT_WAIT = 30  # seconds to wait on 429

_TOKEN_DIR = Path("/tmp/garth_tokens")
_bootstrap_log: list[str] = []  # debug breadcrumbs for /garmin/debug endpoint
_auth_failure_until: float = 0  # epoch timestamp — skip auth attempts until this time
_AUTH_BACKOFF_SECS = 300  # 5 min backoff after auth failure to avoid Garmin 429 spiral


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


def get_garth_client():
    """Login to Garmin Connect via garth, reuse session if possible.

    Priority:
    1. Decode GARTH_TOKENS env var to disk (if set)
    2. Resume from token files on disk
    3. If resume succeeds but API returns 401, try refresh_oauth2
    4. If refresh fails, try fresh login with GARMIN_EMAIL/PASSWORD
    """
    global _auth_failure_until

    # If we recently failed auth, don't hammer Garmin again
    if _auth_failure_until > time.time():
        wait = int(_auth_failure_until - time.time())
        raise RuntimeError(
            f"Garmin auth is in backoff mode (retry in {wait}s) to avoid 429 rate-limit spiral"
        )

    # Always try to decode env var first — tokens may have been refreshed
    if not _TOKEN_DIR.exists():
        _decode_garth_tokens()

    # Try resume from token dir
    if _TOKEN_DIR.exists():
        try:
            garth.resume(str(_TOKEN_DIR))
            _bootstrap_log.append(f"Resumed garth session from {_TOKEN_DIR}")

            # Only refresh if token is actually expired
            if garth.client.oauth2_token.expired:
                _bootstrap_log.append(f"Access token expired (expires_at={garth.client.oauth2_token.expires_at}), attempting refresh_oauth2...")
                try:
                    garth.client.refresh_oauth2()
                    garth.save(str(_TOKEN_DIR))
                    _bootstrap_log.append("Token refresh succeeded, saved to disk")
                except Exception as refresh_err:
                    _bootstrap_log.append(f"Token refresh failed: {refresh_err}")
                    if settings.GARMIN_EMAIL and settings.GARMIN_PASSWORD:
                        _bootstrap_log.append("Attempting fresh login fallback...")
                        try:
                            garth.login(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)
                            garth.save(str(_TOKEN_DIR))
                            _bootstrap_log.append("Fresh login fallback succeeded")
                        except Exception as login_err:
                            _bootstrap_log.append(f"Fresh login fallback failed: {login_err}")
                            _auth_failure_until = time.time() + _AUTH_BACKOFF_SECS
                            _bootstrap_log.append(f"Auth backoff engaged for {_AUTH_BACKOFF_SECS}s")
                            raise RuntimeError(f"All auth methods failed. Refresh: {refresh_err}, Login: {login_err}")
                    else:
                        _auth_failure_until = time.time() + _AUTH_BACKOFF_SECS
                        _bootstrap_log.append(f"Auth backoff engaged for {_AUTH_BACKOFF_SECS}s")
                        raise RuntimeError(f"Token refresh failed and no GARMIN_EMAIL/PASSWORD for fallback: {refresh_err}")
            else:
                _bootstrap_log.append(f"Access token still valid (expires_at={garth.client.oauth2_token.expires_at}), skipping refresh")

            # Verify API access with a real call
            test_status, test_data, test_err = _test_api_call()
            if test_status == "ok":
                _bootstrap_log.append(f"API test OK via {API_TEST_URL}")
            elif test_status == "401":
                _bootstrap_log.append(f"API test got 401 (auth failed), attempting refresh_oauth2...")
                try:
                    garth.client.refresh_oauth2()
                    garth.save(str(_TOKEN_DIR))
                    _bootstrap_log.append("Post-401 refresh succeeded")
                    retry_status, _, retry_err = _test_api_call()
                    if retry_status == "ok":
                        _bootstrap_log.append("API test OK after refresh")
                    else:
                        _bootstrap_log.append(f"API still failing after refresh: {retry_err}")
                except Exception as refresh_err:
                    _bootstrap_log.append(f"Post-401 refresh failed: {refresh_err}")
            else:
                # Non-auth error (404, 429, etc) — don't try refresh
                _bootstrap_log.append(f"API test failed (non-auth error): {test_err}")

            return garth
        except RuntimeError:
            raise
        except Exception as e:
            _bootstrap_log.append(f"Resume failed from {_TOKEN_DIR}: {e}")

    # Fallback: fresh login
    if not settings.GARMIN_EMAIL or not settings.GARMIN_PASSWORD:
        raise RuntimeError(
            "Cannot authenticate to Garmin: no GARTH_TOKENS, no saved tokens, "
            "and GARMIN_EMAIL/GARMIN_PASSWORD not set"
        )
    _bootstrap_log.append("Attempting fresh login with GARMIN_EMAIL/PASSWORD...")
    garth.login(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)
    _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    garth.save(str(_TOKEN_DIR))
    _bootstrap_log.append("Fresh login successful, tokens saved")
    return garth


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
    """Call a garth API function; retry once after 30s on 429."""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if not _is_rate_limit(e):
            raise
        logger.warning("Garmin 429 rate limit hit, waiting %ds before retry", RATE_LIMIT_WAIT)
        time.sleep(RATE_LIMIT_WAIT)
        try:
            return func(*args, **kwargs)
        except Exception as e2:
            if _is_rate_limit(e2):
                raise GarminRateLimitError("Garmin rate limit (429) after retry") from e2
            raise


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
