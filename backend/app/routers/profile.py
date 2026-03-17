from datetime import datetime
from enum import Enum
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.database import AthleteProfile, User

router = APIRouter()


class PowerMeterType(str, Enum):
    dual = "dual"
    left_only = "left_only"
    right_only = "right_only"
    spider = "spider"
    hub = "hub"
    pedals = "pedals"


class ProfileResponse(BaseModel):
    athlete_id: str
    name: str
    ftp_watts: int = Field(ge=50, le=500)
    max_hr: int = Field(ge=120, le=230)
    resting_hr: int | None = None
    weight_kg: float = Field(ge=35, le=150)
    target_ftp_watts: int | None = None
    target_weight_kg: float | None = None
    weekly_hours_budget: float | None = None
    power_meter_type: PowerMeterType | None = None
    goals_text: str | None = None
    preferred_language: Literal["en", "it", "de", "es", "fr"] = "en"
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    ftp_watts: int | None = Field(default=None, ge=50, le=500)
    max_hr: int | None = Field(default=None, ge=120, le=230)
    resting_hr: int | None = None
    weight_kg: float | None = Field(default=None, ge=35, le=150)
    target_ftp_watts: int | None = None
    target_weight_kg: float | None = None
    weekly_hours_budget: float | None = None
    power_meter_type: PowerMeterType | None = None
    goals_text: str | None = None
    preferred_language: Literal["en", "it", "de", "es", "fr"] | None = None


def _profile_to_response(profile: AthleteProfile, user: User) -> ProfileResponse:
    return ProfileResponse(
        athlete_id=profile.user_id,
        name=user.name,
        ftp_watts=profile.ftp_watts,
        max_hr=profile.max_hr,
        resting_hr=profile.resting_hr,
        weight_kg=profile.weight_kg,
        target_ftp_watts=profile.target_ftp_watts,
        target_weight_kg=profile.target_weight_kg,
        weekly_hours_budget=profile.weekly_hours_budget,
        power_meter_type=profile.power_meter_type,
        goals_text=profile.goals_text,
        preferred_language=profile.preferred_language,
        updated_at=profile.updated_at,
    )


async def _get_or_create_profile(user: User, db: AsyncSession) -> AthleteProfile:
    result = await db.execute(
        select(AthleteProfile).where(AthleteProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is not None:
        return profile

    profile = AthleteProfile(user_id=user.id)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_or_create_profile(current_user, db)
    return _profile_to_response(profile, current_user)


@router.put("", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_or_create_profile(current_user, db)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    profile.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(profile)
    return _profile_to_response(profile, current_user)
