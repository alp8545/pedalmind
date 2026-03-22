import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.database import AthleteProfile, Ride, RideAnalysis, User

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RideSummaryResponse(BaseModel):
    id: str
    garmin_activity_id: str | None = None
    ride_date: datetime
    duration_sec: int
    distance_km: float
    has_analysis: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RideListResponse(BaseModel):
    rides: list[RideSummaryResponse]
    total: int
    page: int
    per_page: int


class RideDetailResponse(BaseModel):
    id: str
    garmin_activity_id: str | None = None
    ride_date: datetime
    duration_sec: int
    distance_km: float
    ride_data_json: dict[str, Any]
    analysis_json: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RideDataSummary(BaseModel):
    duration_sec: int
    distance_km: float
    elevation_gain_m: int | None = None
    avg_power_w: int | None = None
    normalized_power_w: int | None = None
    max_power_w: int | None = None
    intensity_factor: float | None = None
    training_stress_score: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_cadence: int | None = None


class RideDataUpload(BaseModel):
    version: str = "1.0"
    ride_id: str
    athlete_id: str
    garmin_activity_id: str | None = None
    timestamp: datetime
    summary: RideDataSummary
    zones: dict[str, Any] = {}
    power_curve: dict[str, Any] | None = None
    intervals: list[Any] = []
    cardiac_decoupling_pct: float | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_athlete_profile_dict(user: User, db: AsyncSession) -> dict:
    result = await db.execute(
        select(AthleteProfile).where(AthleteProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        return {"athlete_id": user.id, "name": user.name, "ftp_watts": 265, "max_hr": 192, "resting_hr": 57, "weight_kg": 68.0, "preferred_language": "en"}
    return {
        "athlete_id": user.id,
        "name": user.name,
        "ftp_watts": profile.ftp_watts,
        "max_hr": profile.max_hr,
        "resting_hr": profile.resting_hr,
        "weight_kg": profile.weight_kg,
        "power_meter_type": profile.power_meter_type,
        "goals_text": profile.goals_text,
        "preferred_language": profile.preferred_language,
    }


async def _get_recent_rides_data(user_id: str, db: AsyncSession, days: int = 7) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(Ride)
        .where(Ride.user_id == user_id, Ride.ride_date >= cutoff)
        .order_by(Ride.ride_date.desc())
        .limit(20)
    )
    return [r.ride_data_json for r in result.scalars().all()]


async def _run_analysis(ride: Ride, user: User, db: AsyncSession) -> dict | None:
    """Run AI analysis and store result. Returns analysis dict or None on failure."""
    from ai_engine.service import analyze_ride

    try:
        profile_dict = await _get_athlete_profile_dict(user, db)
        recent = await _get_recent_rides_data(user.id, db)
        analysis_dict = await analyze_ride(
            ride_data=ride.ride_data_json,
            athlete_profile=profile_dict,
            recent_rides=recent,
            model=settings.AI_MODEL_ANALYSIS,
            api_key=settings.ANTHROPIC_API_KEY,
        )

        # Delete existing analysis if reanalyzing
        if ride.analysis is not None:
            await db.delete(ride.analysis)
            await db.flush()

        ride_analysis = RideAnalysis(
            ride_id=ride.id,
            model_used=analysis_dict.get("model_used", settings.AI_MODEL_ANALYSIS),
            analysis_json=analysis_dict,
            tokens_input=analysis_dict.get("tokens_input"),
            tokens_output=analysis_dict.get("tokens_output"),
        )
        db.add(ride_analysis)
        await db.commit()
        await db.refresh(ride_analysis)
        return analysis_dict
    except Exception:
        logger.exception("AI analysis failed for ride %s", ride.id)
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=RideListResponse)
async def list_rides(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total_result = await db.execute(
        select(func.count()).select_from(Ride).where(Ride.user_id == current_user.id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(Ride)
        .options(selectinload(Ride.analysis))
        .where(Ride.user_id == current_user.id)
        .order_by(Ride.ride_date.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rides = result.scalars().all()

    return RideListResponse(
        rides=[
            RideSummaryResponse(
                id=r.id,
                garmin_activity_id=r.garmin_activity_id,
                ride_date=r.ride_date,
                duration_sec=r.duration_sec,
                distance_km=r.distance_km,
                has_analysis=r.analysis is not None,
                created_at=r.created_at,
            )
            for r in rides
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{ride_id}", response_model=RideDetailResponse)
async def get_ride(
    ride_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Ride)
        .options(selectinload(Ride.analysis))
        .where(Ride.id == ride_id, Ride.user_id == current_user.id)
    )
    ride = result.scalar_one_or_none()
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")

    return RideDetailResponse(
        id=ride.id,
        garmin_activity_id=ride.garmin_activity_id,
        ride_date=ride.ride_date,
        duration_sec=ride.duration_sec,
        distance_km=ride.distance_km,
        ride_data_json=ride.ride_data_json,
        analysis_json=ride.analysis.analysis_json if ride.analysis else None,
        created_at=ride.created_at,
    )


@router.post("/{ride_id}/reanalyze", status_code=status.HTTP_202_ACCEPTED)
async def reanalyze_ride(
    ride_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Ride)
        .options(selectinload(Ride.analysis))
        .where(Ride.id == ride_id, Ride.user_id == current_user.id)
    )
    ride = result.scalar_one_or_none()
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")

    analysis_dict = await _run_analysis(ride, current_user, db)
    if analysis_dict is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI analysis failed")

    return {"status": "completed", "ride_id": ride_id, "analysis": analysis_dict}


@router.post("/upload", response_model=RideDetailResponse, status_code=status.HTTP_201_CREATED)
async def upload_ride(
    body: RideDataUpload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Strip timezone info — DB uses naive timestamps
    ride_date = body.timestamp.replace(tzinfo=None)
    ride = Ride(
        user_id=current_user.id,
        garmin_activity_id=body.garmin_activity_id,
        ride_date=ride_date,
        duration_sec=body.summary.duration_sec,
        distance_km=body.summary.distance_km,
        ride_data_json=body.model_dump(mode="json"),
    )
    db.add(ride)
    await db.commit()
    await db.refresh(ride)

    # Trigger AI analysis — failure is non-blocking
    analysis_dict = await _run_analysis(ride, current_user, db)

    return RideDetailResponse(
        id=ride.id,
        garmin_activity_id=ride.garmin_activity_id,
        ride_date=ride.ride_date,
        duration_sec=ride.duration_sec,
        distance_km=ride.distance_km,
        ride_data_json=ride.ride_data_json,
        analysis_json=analysis_dict,
        created_at=ride.created_at,
    )
