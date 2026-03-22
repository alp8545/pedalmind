"""Garmin Connect API client.

Supports three modes (tried in order):
1. Garth tokens from GARTH_TOKENS env var (base64-encoded, for Railway)
2. Garth token refresh + re-login with GARMIN_EMAIL/PASSWORD
3. OAuth 1.0a with per-user access tokens from the DB

The garth mode uses Garmin Connect's internal API via session cookies.
The OAuth mode calls Garmin's Health API with signed requests.
"""

import base64
import json
import logging
import os
import zipfile
from pathlib import Path

import garth
from requests_oauthlib import OAuth1Session

from app.core.config import settings

logger = logging.getLogger("garmin_client")

FIT_DIR = Path("/tmp/pedalmind_fits")
GARTH_TOKEN_DIR = Path("/tmp/garth_tokens")

GARMIN_API_BASE = "https://apis.garmin.com"

_garth_initialized = False


def _init_garth() -> bool:
    """Initialize garth from GARTH_TOKENS env var or saved tokens.

    Strategy:
    1. If GARTH_TOKENS env var exists (base64), decode and save to disk, then resume
    2. If resume fails, try login with GARMIN_EMAIL/PASSWORD and update tokens
    3. Return True if garth is ready, False otherwise
    """
    global _garth_initialized
    if _garth_initialized:
        return True

    garth_b64 = os.environ.get("GARTH_TOKENS", "")
    garmin_email = os.environ.get("GARMIN_EMAIL", "")
    garmin_password = os.environ.get("GARMIN_PASSWORD", "")

    # Step 1: Try to restore tokens from env var
    if garth_b64:
        try:
            bundle = json.loads(base64.b64decode(garth_b64))
            GARTH_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            for fname, content in bundle.items():
                (GARTH_TOKEN_DIR / fname).write_text(json.dumps(content))
            logger.info("Garth tokens decoded from GARTH_TOKENS env var")
        except Exception:
            logger.exception("Failed to decode GARTH_TOKENS env var")

    # Step 2: Try to resume from saved tokens
    if GARTH_TOKEN_DIR.exists():
        try:
            garth.resume(str(GARTH_TOKEN_DIR))
            # Validate the session with a simple call
            garth.connectapi("/userprofile-service/usersettings")
            _garth_initialized = True
            logger.info("Garth session resumed successfully")
            return True
        except Exception:
            logger.warning("Garth resume failed, will try fresh login")

    # Step 3: Fresh login as fallback
    if garmin_email and garmin_password:
        try:
            garth.login(garmin_email, garmin_password)
            GARTH_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            garth.save(str(GARTH_TOKEN_DIR))
            _garth_initialized = True
            logger.info("Garth fresh login successful")
            return True
        except Exception:
            logger.exception("Garth fresh login failed")

    return False


def get_activities_garth(days: int = 21, max_activities: int = 100) -> list[dict]:
    """Fetch recent activities via garth (Connect API)."""
    if not _init_garth():
        return []
    activities = garth.connectapi(
        "/activitylist-service/activities/search/activities",
        params={"limit": max_activities, "start": 0},
    )
    return activities or []


def download_fit_garth(activity_id: int | str) -> str | None:
    """Download a FIT file via garth. Returns file path or None."""
    if not _init_garth():
        return None

    FIT_DIR.mkdir(parents=True, exist_ok=True)
    fit_path = FIT_DIR / f"garth_{activity_id}.fit"

    if fit_path.exists():
        logger.info("Already downloaded: %s", fit_path.name)
        return str(fit_path)

    try:
        data = garth.download(f"/download-service/files/activity/{activity_id}")
    except Exception:
        logger.exception("Garth download failed for activity %s", activity_id)
        return None

    # Try as zip first, fall back to raw FIT
    zip_path = str(fit_path) + ".zip"
    with open(zip_path, "wb") as f:
        f.write(data)

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            fit_names = [n for n in z.namelist() if n.endswith(".fit")]
            if fit_names:
                with open(fit_path, "wb") as f:
                    f.write(z.read(fit_names[0]))
        os.remove(zip_path)
    except zipfile.BadZipFile:
        os.rename(zip_path, str(fit_path))

    logger.info("Downloaded via garth: %s (%d bytes)", fit_path.name, fit_path.stat().st_size)
    return str(fit_path)


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
