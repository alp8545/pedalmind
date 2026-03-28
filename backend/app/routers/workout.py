"""Workout interpretation (via Anthropic AI) and upload to Garmin Connect.

Two endpoints:
  POST /interpret — natural language → structured workout JSON
  POST /upload   — structured JSON → Garmin Connect workout
"""

import json
import logging
from typing import Optional

import anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
- "sotto soglia" with specific W → power.range centered on that W (±5W)
- "Zona bassa" modifier → lower limit of zone + 20W (±10W range)
- "Zona alta" modifier → upper limit of zone - 20W (±10W range)
- "rapporto lungo" = low cadence 65-80rpm
- "rapporto agile" = high cadence 90-100rpm
- If a single watt value is given (e.g. "230W"), use power.range with ±5W
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

_step_order_counter = 0


def _reset_step_order():
    global _step_order_counter
    _step_order_counter = 0


def _next_step_order() -> int:
    global _step_order_counter
    _step_order_counter += 1
    return _step_order_counter


def _build_target_type(target: PowerTarget | None) -> dict:
    """Build Garmin targetType dict from our PowerTarget model."""
    if not target:
        return {
            "workoutTargetTypeId": 1,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        }

    if target.type == "power.zone":
        return {
            "workoutTargetTypeId": 5,
            "workoutTargetTypeKey": "power.zone",
            "displayOrder": 1,
            "targetValueOne": float(target.value or 0),
            "targetValueTwo": 0.0,
        }
    elif target.type == "power.range":
        return {
            "workoutTargetTypeId": 5,
            "workoutTargetTypeKey": "power.zone",
            "displayOrder": 1,
            "targetValueOne": float(target.value_low or 0),
            "targetValueTwo": float(target.value_high or 0),
        }
    elif target.type == "heart.rate.zone":
        return {
            "workoutTargetTypeId": 2,
            "workoutTargetTypeKey": "heart.rate.zone",
            "displayOrder": 1,
            "targetValueOne": float(target.value or 0),
            "targetValueTwo": 0.0,
        }
    return {
        "workoutTargetTypeId": 1,
        "workoutTargetTypeKey": "no.target",
        "displayOrder": 1,
    }


def _build_cadence_target(cadence: CadenceTarget | None) -> dict | None:
    """Build Garmin secondaryTargetType dict for cadence."""
    if not cadence:
        return None
    return {
        "workoutTargetTypeId": 3,
        "workoutTargetTypeKey": "cadence.zone",
        "displayOrder": 1,
        "targetValueOne": float(cadence.low),
        "targetValueTwo": float(cadence.high),
    }


def _convert_step(step: WorkoutStep):
    """Convert a WorkoutStep pydantic model to a garminconnect workout step."""
    from garminconnect.workout import ExecutableStep, RepeatGroup, StepType, ConditionType

    if step.type == "repeat":
        sub_steps = [_convert_step(s) for s in (step.steps or [])]
        order = _next_step_order()
        return RepeatGroup(
            stepOrder=order,
            stepType={
                "stepTypeId": StepType.REPEAT,
                "stepTypeKey": "repeat",
                "displayOrder": 6,
            },
            numberOfIterations=step.iterations or 1,
            workoutSteps=sub_steps,
            endCondition={
                "conditionTypeId": ConditionType.ITERATIONS,
                "conditionTypeKey": "iterations",
                "displayOrder": 7,
                "displayable": False,
            },
            endConditionValue=float(step.iterations or 1),
        )

    # type == "interval"
    order = _next_step_order()
    kwargs = dict(
        stepOrder=order,
        stepType={
            "stepTypeId": StepType.INTERVAL,
            "stepTypeKey": "interval",
            "displayOrder": 3,
        },
        endCondition={
            "conditionTypeId": ConditionType.TIME,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        },
        endConditionValue=float(step.duration_secs or 0),
        targetType=_build_target_type(step.target),
    )

    cadence_target = _build_cadence_target(step.cadence)
    if cadence_target:
        kwargs["secondaryTargetType"] = cadence_target

    return ExecutableStep(**kwargs)


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
async def upload_workout(req: WorkoutUploadRequest):
    """Convert structured workout to Garmin format and upload."""
    from garminconnect.workout import CyclingWorkout, RunningWorkout, WorkoutSegment, SportType

    w = req.workout

    if w.sport not in ("cycling", "running"):
        raise HTTPException(status_code=400, detail=f"Unsupported sport: {w.sport}")

    _reset_step_order()
    converted_steps = [_convert_step(step) for step in w.steps]

    sport_type_id = SportType.CYCLING if w.sport == "cycling" else SportType.RUNNING
    sport_type_key = w.sport

    segment = WorkoutSegment(
        segmentOrder=1,
        sportType={
            "sportTypeId": sport_type_id,
            "sportTypeKey": sport_type_key,
        },
        workoutSteps=converted_steps,
    )

    WorkoutClass = CyclingWorkout if w.sport == "cycling" else RunningWorkout
    gw = WorkoutClass(
        workoutName=w.name,
        estimatedDurationInSecs=w.estimated_duration_secs,
        workoutSegments=[segment],
    )

    client = _get_garmin_client()

    try:
        if w.sport == "cycling":
            result = client.upload_cycling_workout(gw)
        else:
            result = client.upload_running_workout(gw)
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

    return WorkoutUploadResponse(
        workout_id=workout_id,
        scheduled=scheduled,
        schedule_date=w.schedule_date if scheduled else None,
    )
