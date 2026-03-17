"""Garmin Connect API client.

Supports two modes:
- OAuth 1.0a (production): uses per-user access tokens from the DB
- Email/password (legacy dev): uses garminconnect library directly

The OAuth mode calls Garmin's APIs with signed requests.
"""

import logging
import os
import zipfile
from pathlib import Path

from requests_oauthlib import OAuth1Session

from app.core.config import settings

logger = logging.getLogger("garmin_client")

FIT_DIR = Path("/tmp/pedalmind_fits")

GARMIN_API_BASE = "https://apis.garmin.com"


def get_oauth_session(access_token: str, access_token_secret: str) -> OAuth1Session:
    """Create an OAuth1-signed session for Garmin API calls."""
    return OAuth1Session(
        settings.GARMIN_CONSUMER_KEY,
        client_secret=settings.GARMIN_CONSUMER_SECRET,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
    )


def get_activities_oauth(
    access_token: str,
    access_token_secret: str,
    days: int = 21,
    max_activities: int = 100,
) -> tuple[OAuth1Session, list[dict]]:
    """Fetch activities using OAuth tokens. Returns (session, activities)."""
    from datetime import datetime, timedelta

    session = get_oauth_session(access_token, access_token_secret)

    start_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    end_ts = int(datetime.now().timestamp())

    url = f"{GARMIN_API_BASE}/wellness-api/rest/activities"
    resp = session.get(url, params={
        "uploadStartTimeInSeconds": start_ts,
        "uploadEndTimeInSeconds": end_ts,
    })
    resp.raise_for_status()

    activities = resp.json() if resp.text else []
    logger.info("Found %d activities in last %d days (OAuth)", len(activities), days)
    return session, activities[:max_activities]


def get_latest_activity_oauth(
    access_token: str,
    access_token_secret: str,
) -> tuple[OAuth1Session, list[dict]]:
    """Fetch the most recent activity using OAuth tokens."""
    session, activities = get_activities_oauth(access_token, access_token_secret, days=7, max_activities=1)
    return session, activities[:1]


def download_fit_oauth(
    session: OAuth1Session,
    activity: dict,
) -> str | None:
    """Download a .FIT file for a single activity using OAuth. Returns file path or None."""
    FIT_DIR.mkdir(parents=True, exist_ok=True)

    # Garmin Health API uses different field names than garminconnect
    aid = str(activity.get("activityId") or activity.get("summaryId", "unknown"))
    start_time = activity.get("startTimeLocal", activity.get("startTimeInSeconds", "unknown"))
    if isinstance(start_time, int):
        from datetime import datetime
        date_str = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d")
    else:
        date_str = str(start_time)[:10]

    sport = activity.get("activityType", "cycling")
    if isinstance(sport, dict):
        sport = sport.get("typeKey", "cycling")

    fit_filename = f"{date_str}_{sport}_{aid}.fit"
    fit_path = FIT_DIR / fit_filename

    if fit_path.exists():
        logger.info("Already downloaded: %s", fit_filename)
        return str(fit_path)

    logger.info("Downloading activity %s (%s)", aid, date_str)

    try:
        url = f"{GARMIN_API_BASE}/wellness-api/rest/activityFile"
        resp = session.get(url, params={"id": aid})
        resp.raise_for_status()
        raw_data = resp.content
    except Exception:
        logger.exception("Failed to download activity %s", aid)
        return None

    # Try as zip first, fall back to raw FIT
    zip_path = str(fit_path) + ".zip"
    with open(zip_path, "wb") as f:
        f.write(raw_data)

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            fit_names = [n for n in z.namelist() if n.endswith(".fit")]
            if fit_names:
                with open(fit_path, "wb") as f:
                    f.write(z.read(fit_names[0]))
        os.remove(zip_path)
    except zipfile.BadZipFile:
        os.rename(zip_path, str(fit_path))

    return str(fit_path)
