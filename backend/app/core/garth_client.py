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


def get_garth_client():
    """Login to Garmin Connect via garth, reuse session if possible.

    Priority:
    1. Decode GARTH_TOKENS env var to disk (if set)
    2. Resume from token files on disk
    3. Fresh login with GARMIN_EMAIL/PASSWORD as fallback
    """
    # Always try to decode env var first — tokens may have been refreshed
    if not _TOKEN_DIR.exists():
        _decode_garth_tokens()

    # Try resume from token dir
    if _TOKEN_DIR.exists():
        try:
            garth.resume(str(_TOKEN_DIR))
            _bootstrap_log.append(f"Resumed garth session from {_TOKEN_DIR}")
            return garth
        except Exception as e:
            _bootstrap_log.append(f"Resume failed from {_TOKEN_DIR}: {e}")

    # Fallback: fresh login
    if not settings.GARMIN_EMAIL or not settings.GARMIN_PASSWORD:
        raise RuntimeError(
            "Cannot authenticate to Garmin: no GARTH_TOKENS, no saved tokens, "
            "and GARMIN_EMAIL/GARMIN_PASSWORD not set"
        )
    garth.login(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)
    _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    garth.save(str(_TOKEN_DIR))
    _bootstrap_log.append("Fresh login successful, tokens saved")
    return garth


def get_bootstrap_debug() -> dict:
    """Return debug info about garth token bootstrap for the /garmin/debug endpoint."""
    token_dir_exists = _TOKEN_DIR.exists()
    token_files = sorted(f.name for f in _TOKEN_DIR.iterdir()) if token_dir_exists else []
    return {
        "garth_tokens_env_set": bool(os.environ.get("GARTH_TOKENS", "")),
        "garth_tokens_env_length": len(os.environ.get("GARTH_TOKENS", "")),
        "token_dir": str(_TOKEN_DIR),
        "token_dir_exists": token_dir_exists,
        "token_files": token_files,
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
