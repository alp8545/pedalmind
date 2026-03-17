"""Garmin Connect client service.

Wraps the garminconnect library to authenticate, download activities,
and download .FIT files. Stores session tokens in ~/.garminconnect/
for reuse across requests.
"""

import logging
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from garminconnect import Garmin

logger = logging.getLogger("garmin_client")

TOKEN_DIR = Path.home() / ".garminconnect"
FIT_DIR = Path("/tmp/pedalmind_fits")


def _get_client(email: str, password: str) -> Garmin:
    """Create and authenticate a Garmin client, reusing saved tokens when possible."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    tokenstore = TOKEN_DIR / "tokens"

    client = Garmin(email, password)

    # Try loading saved session first
    if tokenstore.exists():
        try:
            client.login(tokenstore=str(tokenstore))
            logger.info("Resumed Garmin session from saved tokens")
            return client
        except Exception:
            logger.info("Saved tokens expired, performing fresh login")

    client.login()
    client.garth.dump(str(tokenstore))
    logger.info("Logged in to Garmin Connect and saved tokens")
    return client


def get_activities(
    email: str,
    password: str,
    days: int = 21,
    max_activities: int = 100,
) -> tuple[Garmin, list[dict]]:
    """Login and fetch activities from the last N days.

    Returns (client, activities) so the caller can download FIT files
    using the same authenticated session.
    """
    client = _get_client(email, password)

    activities = client.get_activities(0, max_activities)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    filtered = [
        a for a in activities
        if a.get("startTimeLocal", "")[:10] >= cutoff
    ]

    logger.info("Found %d activities in last %d days", len(filtered), days)
    return client, filtered


def get_latest_activity(
    email: str,
    password: str,
) -> tuple[Garmin, list[dict]]:
    """Login and fetch only the most recent activity."""
    client = _get_client(email, password)
    activities = client.get_activities(0, 1)
    return client, activities


def download_fit(client: Garmin, activity: dict) -> str | None:
    """Download a .FIT file for a single activity. Returns file path or None."""
    FIT_DIR.mkdir(parents=True, exist_ok=True)

    aid = activity["activityId"]
    date_str = activity.get("startTimeLocal", "unknown")[:10]
    sport = activity.get("activityType", {}).get("typeKey", "unknown")
    fit_filename = f"{date_str}_{sport}_{aid}.fit"
    fit_path = FIT_DIR / fit_filename

    if fit_path.exists():
        logger.info("Already downloaded: %s", fit_filename)
        return str(fit_path)

    logger.info("Downloading: %s (%s)", activity.get("activityName", ""), date_str)

    try:
        zip_data = client.download_activity(
            aid, dl_fmt=client.ActivityDownloadFormat.ORIGINAL
        )
    except Exception:
        logger.exception("Failed to download activity %s", aid)
        return None

    zip_path = str(fit_path) + ".zip"
    with open(zip_path, "wb") as f:
        f.write(zip_data)

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            fit_names = [n for n in z.namelist() if n.endswith(".fit")]
            if fit_names:
                with open(fit_path, "wb") as f:
                    f.write(z.read(fit_names[0]))
        os.remove(zip_path)
    except zipfile.BadZipFile:
        # Some activities come as raw .fit, not zipped
        os.rename(zip_path, str(fit_path))

    return str(fit_path)
