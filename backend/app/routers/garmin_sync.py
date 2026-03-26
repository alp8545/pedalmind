"""Garmin activity sync via garth (email/password).

Provides endpoints to download activities from Garmin Connect using
the garth library, compute training metrics, and store them in the
activities table. No OAuth required — uses GARMIN_EMAIL/PASSWORD env vars.
"""

import asyncio
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.garth_client import fetch_activities, fetch_activity_details, get_bootstrap_debug, GarminRateLimitError
from app.models.database import Activity

logger = logging.getLogger(__name__)

router = APIRouter()

# ---- Athlete constants (hardcoded, single user for now) ----
FTP = 265
MAX_HR = 192
RESTING_HR = 57
WEIGHT = 68


def _compute_metrics(activity_data: dict) -> dict:
    """Compute TSS, IF, NP and extract key fields from Garmin API response."""
    summary = activity_data.get("summaryDTO", {})

    avg_power = summary.get("averagePower")
    duration_secs = summary.get("elapsedDuration", summary.get("duration", 0))
    normalized_power = summary.get("normPower") or avg_power

    tss = None
    intensity_factor = None

    if normalized_power and FTP:
        intensity_factor = round(normalized_power / FTP, 3)
        tss = round(
            (duration_secs * normalized_power * intensity_factor) / (FTP * 3600) * 100,
            1,
        )

    start_time_str = summary.get("startTimeLocal")
    start_time = None
    if start_time_str:
        try:
            start_time = datetime.fromisoformat(str(start_time_str).replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            pass

    return {
        "name": activity_data.get("activityName", "Untitled"),
        "sport": activity_data.get("activityTypeDTO", {}).get("typeKey", "unknown"),
        "start_time": start_time,
        "duration_secs": duration_secs,
        "distance_m": summary.get("distance"),
        "avg_hr": _safe_int(summary.get("averageHR")),
        "max_hr": _safe_int(summary.get("maxHR")),
        "avg_power": _safe_int(avg_power),
        "max_power": _safe_int(summary.get("maxPower")),
        "normalized_power": _safe_int(normalized_power),
        "tss": tss,
        "intensity_factor": intensity_factor,
        "avg_cadence": _safe_int(summary.get("averageBikingCadence")),
        "calories": _safe_int(summary.get("calories")),
        "elevation_gain": summary.get("elevationGain"),
        "avg_speed": summary.get("averageSpeed"),
    }


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(round(val))
    except (ValueError, TypeError):
        return None


def _generate_analysis(activity: Activity) -> str:
    """Generate rule-based textual analysis from activity metrics."""
    parts: list[str] = []

    if activity.intensity_factor:
        if activity.intensity_factor < 0.75:
            ride_type = "Recupero attivo"
        elif activity.intensity_factor < 0.85:
            ride_type = "Endurance / Fondo"
        elif activity.intensity_factor < 0.95:
            ride_type = "Tempo / Sweet Spot"
        elif activity.intensity_factor <= 1.05:
            ride_type = "Threshold"
        else:
            ride_type = "VO2max / Race"
        parts.append(f"Tipo: {ride_type}")

    if activity.normalized_power:
        parts.append(
            f"NP: {activity.normalized_power}W | IF: {activity.intensity_factor:.2f} | TSS: {activity.tss:.0f}"
        )

    if activity.avg_power:
        w_kg = round(activity.avg_power / WEIGHT, 2)
        parts.append(f"Potenza media: {activity.avg_power}W ({w_kg} W/kg)")

    if activity.avg_hr and activity.max_hr:
        hr_reserve_pct = round(
            (activity.avg_hr - RESTING_HR) / (MAX_HR - RESTING_HR) * 100
        )
        parts.append(f"HR: {activity.avg_hr}/{activity.max_hr} bpm ({hr_reserve_pct}% HRR)")

    if activity.duration_secs:
        hours = int(activity.duration_secs // 3600)
        mins = int((activity.duration_secs % 3600) // 60)
        parts.append(f"Durata: {hours}h{mins:02d}m")

    if activity.distance_m:
        km = round(activity.distance_m / 1000, 1)
        parts.append(f"Distanza: {km} km")

    if activity.elevation_gain:
        parts.append(f"Dislivello: {activity.elevation_gain:.0f}m")

    if activity.avg_power and activity.avg_hr:
        efficiency = round(activity.avg_power / activity.avg_hr, 2)
        parts.append(f"Efficienza (P/HR): {efficiency}")

    if activity.tss:
        if activity.tss < 100:
            parts.append("Carico leggero — buono per recupero o giornata facile")
        elif activity.tss < 200:
            parts.append("Carico moderato — buon allenamento di sviluppo")
        elif activity.tss < 300:
            parts.append("Carico alto — assicurati di recuperare domani")
        else:
            parts.append("Carico molto alto — 1-2 giorni di recupero consigliati")

    return "\n".join(parts)


# ---- Endpoints ----


@router.get("/debug")
async def garmin_debug():
    """Debug endpoint: show garth token bootstrap status, API test, and filesystem state."""
    from app.core.garth_client import get_garth_client

    result = get_bootstrap_debug()

    # Also show env var preview
    garth_tokens_env = os.environ.get("GARTH_TOKENS", "")
    if garth_tokens_env:
        result["garth_tokens_env_preview"] = garth_tokens_env[:50] + "..."

    # Trigger bootstrap and test API
    api_test = {"status": "not_tested"}
    try:
        client = await asyncio.to_thread(get_garth_client)
        api_test["bootstrap"] = "ok"

        # Lightweight API test
        try:
            profile = await asyncio.to_thread(
                client.connectapi, "/userprofile-service/usersummary"
            )
            api_test["status"] = "ok"
            api_test["display_name"] = profile.get("displayName", "?")
        except Exception as api_err:
            api_test["status"] = "api_failed"
            api_test["error"] = str(api_err)

            # Try refresh and retry
            try:
                await asyncio.to_thread(client.client.refresh_oauth2)
                profile = await asyncio.to_thread(
                    client.connectapi, "/userprofile-service/usersummary"
                )
                api_test["status"] = "ok_after_refresh"
                api_test["display_name"] = profile.get("displayName", "?")
            except Exception as refresh_err:
                api_test["refresh_error"] = str(refresh_err)

    except Exception as boot_err:
        api_test["bootstrap"] = "failed"
        api_test["error"] = str(boot_err)
        api_test["traceback"] = traceback.format_exc()

    result["api_test_result"] = api_test
    # Re-fetch bootstrap log after bootstrap attempt
    result["bootstrap_log"] = get_bootstrap_debug()["bootstrap_log"]

    return result


@router.post("/sync/last")
async def sync_last_ride(db: AsyncSession = Depends(get_db)):
    """Download the latest activity from Garmin and save to DB."""
    try:
        activities = await asyncio.to_thread(fetch_activities, days=3, limit=5)
    except GarminRateLimitError:
        logger.warning("Garmin rate limit on sync/last")
        raise HTTPException(
            status_code=429,
            detail="Garmin è temporaneamente sovraccarico, riprova tra qualche minuto",
        )
    except Exception as e:
        logger.exception("Garmin garth connection failed")
        raise HTTPException(status_code=502, detail=f"Errore connessione Garmin: {e}")

    if not activities:
        raise HTTPException(status_code=404, detail="Nessuna attivita trovata")

    latest = activities[0]
    activity_id = latest["activityId"]

    existing = await db.execute(select(Activity).where(Activity.id == activity_id))
    if existing.scalar_one_or_none():
        return {"message": "Attivita gia scaricata", "activity_id": activity_id, "skipped": True}

    details = await asyncio.to_thread(fetch_activity_details, activity_id)
    metrics = _compute_metrics(details)

    activity = Activity(
        id=activity_id,
        raw_data=details,
        splits_data=details.get("splits"),
        **metrics,
    )
    db.add(activity)
    await db.commit()

    return {"message": "Attivita scaricata", "activity_id": activity_id, "metrics": metrics}


@router.post("/sync/weeks/{weeks}")
async def sync_weeks(weeks: int = 3, db: AsyncSession = Depends(get_db)):
    """Download all activities from the last N weeks."""
    days = weeks * 7

    try:
        activities = await asyncio.to_thread(fetch_activities, days=days, limit=100)
    except GarminRateLimitError:
        logger.warning("Garmin rate limit on sync/weeks/%d", weeks)
        raise HTTPException(
            status_code=429,
            detail="Garmin è temporaneamente sovraccarico, riprova tra qualche minuto",
        )
    except Exception as e:
        logger.exception("Garmin garth connection failed")
        raise HTTPException(status_code=502, detail=f"Errore connessione Garmin: {e}")

    synced = []
    skipped = []

    for act in activities:
        activity_id = act["activityId"]

        existing = await db.execute(select(Activity).where(Activity.id == activity_id))
        if existing.scalar_one_or_none():
            skipped.append(activity_id)
            continue

        try:
            details = await asyncio.to_thread(fetch_activity_details, activity_id)
            metrics = _compute_metrics(details)

            activity = Activity(
                id=activity_id,
                raw_data=details,
                splits_data=details.get("splits"),
                **metrics,
            )
            db.add(activity)
            synced.append({"activity_id": activity_id, **metrics})
        except Exception as e:
            logger.warning("Error syncing activity %s: %s", activity_id, e)
            continue

    await db.commit()

    return {
        "synced": len(synced),
        "skipped": len(skipped),
        "activities": synced,
    }


@router.get("/activities")
async def list_activities(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """List activities stored in DB, newest first."""
    result = await db.execute(
        select(Activity).order_by(Activity.start_time.desc()).limit(limit)
    )
    activities = result.scalars().all()

    return [
        {
            "id": a.id,
            "name": a.name,
            "sport": a.sport,
            "start_time": a.start_time.isoformat() if a.start_time else None,
            "duration_secs": a.duration_secs,
            "distance_m": a.distance_m,
            "avg_power": a.avg_power,
            "normalized_power": a.normalized_power,
            "tss": a.tss,
            "intensity_factor": a.intensity_factor,
            "avg_hr": a.avg_hr,
            "avg_cadence": a.avg_cadence,
            "elevation_gain": a.elevation_gain,
            "analyzed": a.analyzed,
        }
        for a in activities
    ]


@router.get("/activities/{activity_id}")
async def get_activity(activity_id: int, db: AsyncSession = Depends(get_db)):
    """Full detail for a single activity (for analysis view)."""
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()

    if not activity:
        raise HTTPException(status_code=404, detail="Attivita non trovata")

    return {
        "id": activity.id,
        "name": activity.name,
        "sport": activity.sport,
        "start_time": activity.start_time.isoformat() if activity.start_time else None,
        "duration_secs": activity.duration_secs,
        "distance_m": activity.distance_m,
        "avg_power": activity.avg_power,
        "normalized_power": activity.normalized_power,
        "max_power": activity.max_power,
        "tss": activity.tss,
        "intensity_factor": activity.intensity_factor,
        "avg_hr": activity.avg_hr,
        "max_hr": activity.max_hr,
        "avg_cadence": activity.avg_cadence,
        "calories": activity.calories,
        "elevation_gain": activity.elevation_gain,
        "avg_speed": activity.avg_speed,
        "splits_data": activity.splits_data,
        "analyzed": activity.analyzed,
        "analysis_text": activity.analysis_text,
        "raw_data": activity.raw_data,
    }


@router.post("/activities/{activity_id}/analyze")
async def analyze_activity(activity_id: int, db: AsyncSession = Depends(get_db)):
    """Generate rule-based analysis for an activity.

    In the future this will call Anthropic API for AI-powered coaching.
    """
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()

    if not activity:
        raise HTTPException(status_code=404, detail="Attivita non trovata")

    analysis = _generate_analysis(activity)

    activity.analyzed = True
    activity.analysis_text = analysis
    await db.commit()

    return {"activity_id": activity_id, "analysis": analysis}
