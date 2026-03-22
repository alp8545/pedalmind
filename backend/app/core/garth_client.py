"""Garmin Connect client using garth (email/password auth).

Uses garth library for simpler auth flow — no OAuth setup required.
Token is cached in ~/.garth/ and re-used across requests.
If the token expires, garth re-authenticates automatically.
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import garth
from garth.exc import GarthHTTPError

from app.core.config import settings

logger = logging.getLogger("garth_client")

RATE_LIMIT_WAIT = 30  # seconds to wait on 429

_TOKEN_DIR = str(Path.home() / ".garth")


def get_garth_client():
    """Login to Garmin Connect via garth, reuse session if possible."""
    try:
        garth.resume(_TOKEN_DIR)
        logger.debug("Resumed garth session from %s", _TOKEN_DIR)
    except Exception:
        if not settings.GARMIN_EMAIL or not settings.GARMIN_PASSWORD:
            raise RuntimeError(
                "GARMIN_EMAIL and GARMIN_PASSWORD must be set for garth sync"
            )
        garth.login(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)
        garth.save(_TOKEN_DIR)
        logger.info("Logged in to Garmin via garth and saved session")
    return garth


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
