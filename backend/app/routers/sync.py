"""Garmin Connect sync endpoints.

Downloads activities from Garmin, parses .FIT files into RideData,
and stores them in the DB. Skips AI analysis for speed — user can
reanalyze individual rides later via POST /api/rides/:id/reanalyze.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.garmin_client import download_fit, get_activities, get_latest_activity
from app.core.security import get_current_user
from app.models.database import AthleteProfile, Ride, User

logger = logging.getLogger(__name__)

router = APIRouter()


class SyncResult(BaseModel):
    imported: int
    skipped: int
    failed: int
    rides: list[str]  # list of ride IDs that were imported


async def _get_profile_defaults(user: User, db: AsyncSession) -> dict:
    """Get athlete profile values needed for FIT parsing."""
    result = await db.execute(
        select(AthleteProfile).where(AthleteProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile:
        return {
            "ftp": profile.ftp_watts,
            "max_hr": profile.max_hr,
            "resting_hr": profile.resting_hr or 0,
            "weight_kg": profile.weight_kg,
        }
    return {"ftp": 200, "max_hr": 190, "resting_hr": 0, "weight_kg": 70.0}


async def _import_activities(
    client,
    activities: list[dict],
    user: User,
    db: AsyncSession,
) -> SyncResult:
    """Download, parse, and store activities. Skip duplicates by garmin_activity_id."""
    from garmin_sync.worker import parse_fit_file

    profile = await _get_profile_defaults(user, db)
    imported_ids: list[str] = []
    skipped = 0
    failed = 0

    for activity in activities:
        aid = str(activity["activityId"])

        # Check for duplicate
        existing = await db.execute(
            select(Ride).where(
                Ride.user_id == user.id,
                Ride.garmin_activity_id == aid,
            )
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue

        # Download .FIT file
        fit_path = download_fit(client, activity)
        if fit_path is None:
            failed += 1
            continue

        # Parse .FIT file
        try:
            ride_data = parse_fit_file(
                fit_path=fit_path,
                ftp=profile["ftp"],
                max_hr=profile["max_hr"],
                resting_hr=profile["resting_hr"],
                weight_kg=profile["weight_kg"],
                athlete_id=user.id,
                garmin_activity_id=aid,
            )
        except Exception:
            logger.exception("Failed to parse FIT file for activity %s", aid)
            failed += 1
            continue

        if not ride_data:
            failed += 1
            continue

        # Parse ride date
        ts = ride_data.get("timestamp")
        try:
            ride_date = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            ride_date = datetime.utcnow()

        ride = Ride(
            user_id=user.id,
            garmin_activity_id=aid,
            ride_date=ride_date,
            duration_sec=ride_data.get("summary", {}).get("duration_sec", 0),
            distance_km=ride_data.get("summary", {}).get("distance_km", 0.0),
            ride_data_json=ride_data,
        )
        db.add(ride)
        await db.flush()
        imported_ids.append(ride.id)

    await db.commit()

    return SyncResult(
        imported=len(imported_ids),
        skipped=skipped,
        failed=failed,
        rides=imported_ids,
    )


def _get_garmin_credentials() -> tuple[str, str]:
    """Get Garmin email/password from settings."""
    email = settings.GARMIN_EMAIL
    password = settings.GARMIN_PASSWORD
    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Garmin credentials not configured. Set GARMIN_EMAIL and GARMIN_PASSWORD in .env",
        )
    return email, password


@router.post("/recent", response_model=SyncResult)
async def sync_recent(
    weeks: int = Query(default=3, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync activities from the last N weeks from Garmin Connect."""
    email, password = _get_garmin_credentials()
    days = weeks * 7

    try:
        client, activities = get_activities(email, password, days=days)
    except Exception as e:
        logger.exception("Garmin login/fetch failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Garmin Connect error: {e}",
        )

    return await _import_activities(client, activities, current_user, db)


@router.post("/latest", response_model=SyncResult)
async def sync_latest(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync only the most recent activity from Garmin Connect."""
    email, password = _get_garmin_credentials()

    try:
        client, activities = get_latest_activity(email, password)
    except Exception as e:
        logger.exception("Garmin login/fetch failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Garmin Connect error: {e}",
        )

    return await _import_activities(client, activities, current_user, db)


@router.get("/status")
async def sync_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check last sync info for the current user."""
    result = await db.execute(
        select(Ride)
        .where(Ride.user_id == current_user.id)
        .order_by(Ride.created_at.desc())
        .limit(1)
    )
    last_ride = result.scalar_one_or_none()
    return {
        "last_sync": last_ride.created_at.isoformat() if last_ride else None,
        "garmin_configured": bool(settings.GARMIN_EMAIL and settings.GARMIN_PASSWORD),
    }
