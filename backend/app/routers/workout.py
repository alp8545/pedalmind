"""Workout interpretation (via Anthropic AI) and upload to Garmin Connect.

Two endpoints:
  POST /interpret — natural language → structured workout JSON
  POST /upload   — structured JSON → Garmin Connect workout
"""

import json
import logging
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class WorkoutInterpretRequest(BaseModel):
    description: str  # es. "sweet spot 2x20 con 5 min recupero"
    sport: str = "cycling"  # "cycling" o "running"
    schedule_date: Optional[str] = None  # "YYYY-MM-DD"


class CadenceTarget(BaseModel):
    low: int
    high: int


class PowerTarget(BaseModel):
    type: str  # "power.zone" | "power.range" | "heart.rate.zone"
    value: Optional[int] = None  # per zone (1-7)
    value_low: Optional[int] = None  # per range
    value_high: Optional[int] = None  # per range


class WorkoutStep(BaseModel):
    type: str  # "interval" | "repeat"
    duration_secs: Optional[int] = None
    target: Optional[PowerTarget] = None
    cadence: Optional[CadenceTarget] = None
    description: Optional[str] = None
    iterations: Optional[int] = None  # for repeat
    steps: Optional[list["WorkoutStep"]] = None  # for repeat


class WorkoutStructured(BaseModel):
    name: str
    sport: str
    estimated_duration_secs: int
    tss_estimate: Optional[int] = None
    schedule_date: Optional[str] = None
    steps: list[WorkoutStep]


class WorkoutUploadRequest(BaseModel):
    workout: WorkoutStructured


class WorkoutUploadResponse(BaseModel):
    workout_id: str
    scheduled: bool
    schedule_date: Optional[str] = None


# ---------------------------------------------------------------------------
# AI system prompt
# ---------------------------------------------------------------------------

INTERPRET_SYSTEM_PROMPT = """\
You are a cycling/running workout interpreter. Convert natural language workout descriptions into structured JSON.

## Athlete Profile
- FTP: 265W
- Power Zones (Coggan): Z1<146W, Z2 146-199W, Z3 199-239W, Z4 239-278W, Z5 278-318W, Z6 318-398W, Z7>398W
- Max HR: 192 bpm, Resting HR: 57 bpm

## Interpretation Rules
- "Sweet spot" = 88-93% FTP = 233-246W → use power.range with value_low=233, value_high=246
- "Soglia" / "threshold" = Z4 = 239-278W
- "VO2max" = Z5 = 278-318W
- "Endurance" / "fondo" = Z2
- "Recupero" = Z1
- "sotto soglia" with specific W → power.range centered on that W (±10W)
- "Zona bassa" / "Z{n} bassa" modifier → lower limit of zone as value_low, +20W as value_high. Example: "Z5 bassa" → power.range value_low=278, value_high=298 (bottom of Z5 + 20W)
- "Zona alta" / "Z{n} alta" modifier → upper limit of zone as value_high, -20W as value_low. Example: "Z5 alta" → power.range value_low=298, value_high=318 (top of Z5 - 20W)
- "rapporto lungo" = low cadence 65-80rpm
- "rapporto agile" = high cadence 90-100rpm
- If a single watt value is given (e.g. "250W"), use power.range with ±10W (e.g. value_low=240, value_high=260)
- If a zone is given (e.g. "Z3"), use power.zone with value=3

## Cadence Rules (cycling only)
Every step MUST have cadence. Defaults if not specified:
- Endurance/recovery: cadence low=85, high=95
- Tempo/threshold: cadence low=90, high=100
- VO2max+: cadence low=90, high=110
If specific RPM given (e.g. "100rpm"): use ±10 range (low=90, high=110)
If RPM range given (e.g. "75-90rpm"): use as-is

## Common Workout Templates (use when description is generic)
- "Sweet Spot" / "SS": 15min WU Z2 → 2x20min @233-246W (5min Z1 rec) → 10min Z1 CD. TSS ~80
- "VO2max": 15min WU Z2 → 5x4min @Z5 (3min Z1 rec) → 10min Z1 CD. TSS ~85
- "Threshold" / "soglia": 15min WU Z2 → 2x15min @Z4 (5min Z1 rec) → 10min Z1 CD. TSS ~75
- "Endurance" / "fondo lungo": 10min WU Z1 → 120min @Z2 → 5min Z1 CD. TSS ~120
- "Sprint": 15min WU Z2 → 8x30s all-out (4:30 Z1 rec) → 15min Z1 CD. TSS ~60

## Output Format
Return ONLY valid JSON, no markdown, no explanation. Schema:
{
  "name": "string — workout name",
  "sport": "cycling" or "running",
  "estimated_duration_secs": integer,
  "tss_estimate": integer or null,
  "steps": [
    {
      "type": "interval",
      "duration_secs": integer,
      "target": {
        "type": "power.zone" or "power.range" or "heart.rate.zone",
        "value": integer or null,
        "value_low": integer or null,
        "value_high": integer or null
      },
      "cadence": { "low": integer, "high": integer },
      "description": "string"
    },
    {
      "type": "repeat",
      "iterations": integer,
      "steps": [ ...same step schema... ]
    }
  ]
}"""

# ---------------------------------------------------------------------------
# Garmin client helper
# ---------------------------------------------------------------------------


def _get_garmin_client():
    """Bootstrap a Garmin Connect client from garth tokens."""
    from app.core.garth_client import get_garth_client
    from garminconnect import Garmin

    get_garth_client()  # ensures garth session is active
    import garth as _garth

    client = Garmin()
    client.garth = _garth.client
    return client


# ---------------------------------------------------------------------------
# Step conversion helpers
# ---------------------------------------------------------------------------

"""
Garmin workout step format (from real API responses):

Power zone target:
  targetType: {workoutTargetTypeId: 2, workoutTargetTypeKey: "power.zone", displayOrder: 2}
  zoneNumber: 3              (zone number, top-level field)
  targetValueOne: null       (null for zone targets)
  targetValueTwo: null

Power range target (custom watts):
  targetType: {workoutTargetTypeId: 2, workoutTargetTypeKey: "power.zone", displayOrder: 2}
  zoneNumber: null
  targetValueOne: 233.0      (low watts)
  targetValueTwo: 246.0      (high watts)

Cadence secondary target:
  secondaryTargetType: {workoutTargetTypeId: 3, workoutTargetTypeKey: "cadence", displayOrder: 3}
  secondaryTargetValueOne: 90.0   (low rpm, top-level)
  secondaryTargetValueTwo: 100.0  (high rpm, top-level)
"""


def _build_step_dict(step: WorkoutStep, step_order: int) -> dict:
    """Build a raw Garmin step dict that matches the real API format exactly."""
    from garminconnect.workout import StepType, ConditionType

    result = {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": {
            "stepTypeId": StepType.INTERVAL,
            "stepTypeKey": "interval",
            "displayOrder": 3,
        },
        "endCondition": {
            "conditionTypeId": ConditionType.TIME,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        },
        "endConditionValue": float(step.duration_secs or 0),
    }

    # Primary target: power zone or power range
    target = step.target
    if target and target.type == "power.zone":
        result["targetType"] = {
            "workoutTargetTypeId": 2,
            "workoutTargetTypeKey": "power.zone",
            "displayOrder": 2,
        }
        result["zoneNumber"] = target.value
        result["targetValueOne"] = None
        result["targetValueTwo"] = None
    elif target and target.type == "power.range":
        result["targetType"] = {
            "workoutTargetTypeId": 2,
            "workoutTargetTypeKey": "power.zone",
            "displayOrder": 2,
        }
        result["zoneNumber"] = None
        result["targetValueOne"] = float(target.value_low or 0)
        result["targetValueTwo"] = float(target.value_high or 0)
    elif target and target.type == "heart.rate.zone":
        result["targetType"] = {
            "workoutTargetTypeId": 4,
            "workoutTargetTypeKey": "heart.rate.zone",
            "displayOrder": 4,
        }
        result["zoneNumber"] = target.value
        result["targetValueOne"] = None
        result["targetValueTwo"] = None
    else:
        result["targetType"] = {
            "workoutTargetTypeId": 1,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        }

    # Secondary target: cadence
    cadence = step.cadence
    if cadence:
        result["secondaryTargetType"] = {
            "workoutTargetTypeId": 3,
            "workoutTargetTypeKey": "cadence",
            "displayOrder": 3,
        }
        result["secondaryTargetValueOne"] = float(cadence.low)
        result["secondaryTargetValueTwo"] = float(cadence.high)

    return result


def _build_repeat_dict(step: WorkoutStep, step_order_start: int) -> tuple[dict, int]:
    """Build a raw Garmin repeat group dict. Returns (dict, next_step_order)."""
    from garminconnect.workout import StepType, ConditionType

    order = step_order_start
    sub_steps = []
    for s in (step.steps or []):
        if s.type == "repeat":
            sub_dict, order = _build_repeat_dict(s, order)
            sub_steps.append(sub_dict)
        else:
            order += 1
            sub_steps.append(_build_step_dict(s, order))

    result = {
        "type": "RepeatGroupDTO",
        "stepOrder": step_order_start,
        "stepType": {
            "stepTypeId": StepType.REPEAT,
            "stepTypeKey": "repeat",
            "displayOrder": 6,
        },
        "numberOfIterations": step.iterations or 1,
        "workoutSteps": sub_steps,
        "endCondition": {
            "conditionTypeId": ConditionType.ITERATIONS,
            "conditionTypeKey": "iterations",
            "displayOrder": 7,
            "displayable": False,
        },
        "endConditionValue": float(step.iterations or 1),
    }
    return result, order


def _convert_steps_to_dicts(steps: list[WorkoutStep]) -> list[dict]:
    """Convert all workout steps to raw Garmin dicts."""
    result = []
    order = 0
    for step in steps:
        if step.type == "repeat":
            order += 1
            repeat_dict, order = _build_repeat_dict(step, order)
            result.append(repeat_dict)
        else:
            order += 1
            result.append(_build_step_dict(step, order))
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/interpret", response_model=WorkoutStructured)
async def interpret_workout(req: WorkoutInterpretRequest):
    """Use Anthropic Haiku to interpret a natural-language workout description."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    user_prompt = f"Interpret this workout: {req.description}\nSport: {req.sport}"

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=INTERPRET_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIError as exc:
        logger.exception("Anthropic API error during workout interpretation")
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}") from exc

    raw_text = message.content[0].text.strip()
    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3].strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("AI returned invalid JSON: %s", raw_text[:500])
        raise HTTPException(status_code=502, detail="AI returned invalid JSON") from exc

    # Propagate schedule_date from request if provided
    if req.schedule_date:
        data["schedule_date"] = req.schedule_date

    return WorkoutStructured(**data)


@router.post("/upload", response_model=WorkoutUploadResponse)
async def upload_workout(req: WorkoutUploadRequest, db: AsyncSession = Depends(get_db)):
    """Convert structured workout to Garmin format, upload, and save to DB."""
    from garminconnect.workout import SportType

    w = req.workout

    if w.sport not in ("cycling", "running"):
        raise HTTPException(status_code=400, detail=f"Unsupported sport: {w.sport}")

    converted_steps = _convert_steps_to_dicts(w.steps)

    sport_type_id = SportType.CYCLING if w.sport == "cycling" else SportType.RUNNING

    workout_dict = {
        "workoutName": w.name,
        "sportType": {
            "sportTypeId": sport_type_id,
            "sportTypeKey": w.sport,
        },
        "estimatedDurationInSecs": w.estimated_duration_secs,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": {
                    "sportTypeId": sport_type_id,
                    "sportTypeKey": w.sport,
                },
                "workoutSteps": converted_steps,
            }
        ],
    }

    client = _get_garmin_client()

    try:
        result = client.upload_workout(workout_dict)
    except Exception as exc:
        logger.exception("Failed to upload workout to Garmin")
        raise HTTPException(status_code=502, detail=f"Garmin upload failed: {exc}") from exc

    workout_id = str(result.get("workoutId", result.get("id", "")))

    scheduled = False
    if w.schedule_date:
        try:
            client.schedule_workout(workout_id, w.schedule_date)
            scheduled = True
        except Exception as exc:
            logger.warning("Workout uploaded but scheduling failed: %s", exc)

    # Save to DB for Piano Settimanale display
    from app.models.database import ScheduledWorkout
    sw = ScheduledWorkout(
        name=w.name,
        sport=w.sport,
        schedule_date=w.schedule_date,
        estimated_duration_secs=w.estimated_duration_secs,
        tss_estimate=w.tss_estimate,
        steps_json=[s.model_dump() for s in w.steps],
        garmin_workout_id=workout_id,
        uploaded=True,
    )
    db.add(sw)
    await db.commit()

    return WorkoutUploadResponse(
        workout_id=workout_id,
        scheduled=scheduled,
        schedule_date=w.schedule_date if scheduled else None,
    )


@router.get("/week")
async def get_week_workouts(
    start_date: str = None,
    db: AsyncSession = Depends(get_db),
):
    """List scheduled workouts for a given week (Mon-Sun).

    If start_date not provided, returns current week.
    """
    from datetime import date, timedelta
    from app.models.database import ScheduledWorkout

    if start_date:
        monday = date.fromisoformat(start_date)
    else:
        today = date.today()
        monday = today - timedelta(days=today.weekday())

    sunday = monday + timedelta(days=6)

    result = await db.execute(
        select(ScheduledWorkout)
        .where(
            ScheduledWorkout.schedule_date >= monday.isoformat(),
            ScheduledWorkout.schedule_date <= sunday.isoformat(),
        )
        .order_by(ScheduledWorkout.schedule_date)
    )
    workouts = result.scalars().all()

    return {
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "workouts": [
            {
                "id": w.id,
                "name": w.name,
                "sport": w.sport,
                "schedule_date": w.schedule_date,
                "estimated_duration_secs": w.estimated_duration_secs,
                "tss_estimate": w.tss_estimate,
                "steps": w.steps_json,
                "uploaded": w.uploaded,
                "completed": w.completed,
                "garmin_workout_id": w.garmin_workout_id,
            }
            for w in workouts
        ],
    }


@router.get("/{workout_id}")
async def get_workout_detail(workout_id: str, db: AsyncSession = Depends(get_db)):
    """Get full workout details including steps."""
    from app.models.database import ScheduledWorkout

    result = await db.execute(
        select(ScheduledWorkout).where(ScheduledWorkout.id == workout_id)
    )
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Workout non trovato")

    return {
        "id": w.id,
        "name": w.name,
        "sport": w.sport,
        "schedule_date": w.schedule_date,
        "estimated_duration_secs": w.estimated_duration_secs,
        "tss_estimate": w.tss_estimate,
        "steps": w.steps_json,
        "uploaded": w.uploaded,
        "completed": w.completed,
        "garmin_workout_id": w.garmin_workout_id,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }
