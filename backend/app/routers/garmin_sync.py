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
from app.core.garth_client import fetch_activities, fetch_activity_details, get_bootstrap_debug, GarminRateLimitError, API_TEST_URL
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
    from datetime import datetime, timezone
    from app.core.garth_client import get_garth_client, _get_http_status

    def _ts():
        return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

    result = get_bootstrap_debug()
    debug_log: list[str] = []

    # Env var preview
    garth_tokens_env = os.environ.get("GARTH_TOKENS", "")
    if garth_tokens_env:
        result["garth_tokens_env_preview"] = garth_tokens_env[:50] + "..."

    # --- Step 1: bootstrap ---
    api_test: dict = {"status": "not_tested"}
    try:
        debug_log.append(f"[{_ts()}] Calling get_garth_client()...")
        client = await asyncio.to_thread(get_garth_client)
        api_test["bootstrap"] = "ok"
        debug_log.append(f"[{_ts()}] Bootstrap OK")
    except Exception as boot_err:
        api_test["bootstrap"] = "failed"
        api_test["error"] = str(boot_err)
        api_test["traceback"] = traceback.format_exc()
        debug_log.append(f"[{_ts()}] Bootstrap FAILED: {boot_err}")
        result["api_test_result"] = api_test
        result["debug_log"] = debug_log
        result["bootstrap_log"] = get_bootstrap_debug()["bootstrap_log"]
        return result

    # --- Step 2: dump oauth2_token details ---
    try:
        tok = client.client.oauth2_token
        api_test["oauth2_token"] = {
            "access_token_preview": tok.access_token[:20] + "...",
            "expires_at": tok.expires_at,
            "expires_at_human": datetime.fromtimestamp(tok.expires_at, tz=timezone.utc).isoformat(),
            "is_expired": tok.expired,
            "refresh_token_preview": tok.refresh_token[:20] + "..." if tok.refresh_token else None,
            "refresh_token_expired": tok.refresh_expired,
        }
        debug_log.append(f"[{_ts()}] Token expires_at={tok.expires_at} expired={tok.expired}")
    except Exception as e:
        api_test["oauth2_token"] = {"error": str(e)}
        debug_log.append(f"[{_ts()}] Failed to read oauth2_token: {e}")

    # --- Step 3: test API call to /userprofile-service/usersummary ---
    profile_url = "/userprofile-service/usersummary"
    debug_log.append(f"[{_ts()}] Testing GET {profile_url}...")
    try:
        profile = await asyncio.to_thread(client.connectapi, profile_url)
        api_test["profile_test"] = {"status": "ok", "url": profile_url, "response_keys": list(profile.keys()) if isinstance(profile, dict) else str(type(profile))}
        debug_log.append(f"[{_ts()}] Profile test OK, keys={list(profile.keys()) if isinstance(profile, dict) else '?'}")
    except Exception as profile_err:
        http_status = _get_http_status(profile_err)
        api_test["profile_test"] = {"status": "failed", "url": profile_url, "http_status": http_status, "error": str(profile_err)}
        debug_log.append(f"[{_ts()}] Profile test FAILED: HTTP {http_status} — {profile_err}")

        # --- Step 4: on 401, try forced refresh and retry ---
        if http_status == 401:
            debug_log.append(f"[{_ts()}] Got 401, attempting forced refresh_oauth2()...")
            try:
                await asyncio.to_thread(client.client.refresh_oauth2)
                debug_log.append(f"[{_ts()}] Refresh OK, retrying {profile_url}...")
                profile = await asyncio.to_thread(client.connectapi, profile_url)
                api_test["profile_test_after_refresh"] = {"status": "ok", "response_keys": list(profile.keys()) if isinstance(profile, dict) else str(type(profile))}
                debug_log.append(f"[{_ts()}] Retry OK after refresh")
            except Exception as retry_err:
                api_test["profile_test_after_refresh"] = {"status": "failed", "error": str(retry_err)}
                debug_log.append(f"[{_ts()}] Retry FAILED after refresh: {retry_err}")

    # --- Step 5: test activitylist endpoint (proven working) ---
    debug_log.append(f"[{_ts()}] Testing GET {API_TEST_URL}?limit=1...")
    try:
        activities = await asyncio.to_thread(
            client.connectapi, API_TEST_URL, params={"limit": 1}
        )
        count = len(activities) if isinstance(activities, list) else "non-list"
        api_test["activity_test"] = {"status": "ok", "url": API_TEST_URL, "activities_returned": count}
        api_test["status"] = "ok"
        debug_log.append(f"[{_ts()}] Activity test OK, returned {count}")
    except Exception as act_err:
        http_status = _get_http_status(act_err)
        api_test["activity_test"] = {"status": "failed", "url": API_TEST_URL, "http_status": http_status, "error": str(act_err)}
        api_test["status"] = "activity_test_failed"
        debug_log.append(f"[{_ts()}] Activity test FAILED: HTTP {http_status} — {act_err}")

    result["api_test_result"] = api_test
    result["debug_log"] = debug_log
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

    try:
        details = await asyncio.to_thread(fetch_activity_details, activity_id)
    except Exception as e:
        logger.exception("Failed to fetch activity details for %s", activity_id)
        raise HTTPException(status_code=502, detail=f"Errore download dettagli attivita: {e}")

    try:
        metrics = _compute_metrics(details)
        activity = Activity(
            id=activity_id,
            raw_data=details,
            splits_data=details.get("splits"),
            **metrics,
        )
        db.add(activity)
        await db.commit()
    except Exception as e:
        logger.exception("Failed to save activity %s to DB", activity_id)
        raise HTTPException(status_code=500, detail=f"Errore salvataggio attivita: {e}")

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


@router.post("/import/bulk")
async def import_bulk_activities(
    activities: list[dict],
    db: AsyncSession = Depends(get_db),
):
    """Import a batch of pre-formatted activities (from garmin-analyzer archive)."""
    existing = await db.execute(select(Activity.id))
    existing_ids = {row[0] for row in existing}

    import math

    def clean_float(v):
        """Replace NaN/Inf with None."""
        if v is None:
            return None
        try:
            f = float(v)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except (ValueError, TypeError):
            return None

    def clean_int(v):
        f = clean_float(v)
        return int(f) if f is not None else None

    inserted = 0
    skipped = 0
    errors = []

    for act in activities:
        act_id = act.get("id")
        if not act_id:
            errors.append("missing id")
            continue
        if act_id in existing_ids:
            skipped += 1
            continue

        try:
            start_time = act.get("start_time")
            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00")).replace(tzinfo=None)
                except (ValueError, TypeError):
                    start_time = None

            activity = Activity(
                id=act_id,
                name=act.get("name") or "Unknown",
                sport=act.get("sport"),
                start_time=start_time,
                duration_secs=clean_float(act.get("duration_secs")),
                distance_m=clean_float(act.get("distance_m")),
                avg_hr=clean_int(act.get("avg_hr")),
                max_hr=clean_int(act.get("max_hr")),
                avg_power=clean_int(act.get("avg_power")),
                max_power=clean_int(act.get("max_power")),
                normalized_power=clean_int(act.get("normalized_power")),
                tss=clean_float(act.get("tss")),
                intensity_factor=clean_float(act.get("intensity_factor")),
                avg_cadence=clean_int(act.get("avg_cadence")),
                calories=clean_int(act.get("calories")),
                elevation_gain=clean_float(act.get("elevation_gain")),
                avg_speed=clean_float(act.get("avg_speed")),
                raw_data=act.get("raw_data", {}),
                splits_data=act.get("splits_data"),
                analyzed=act.get("analyzed", False),
                analysis_text=act.get("analysis_text"),
            )
            db.add(activity)
            await db.flush()
            inserted += 1
            existing_ids.add(act_id)
        except Exception as e:
            await db.rollback()
            errors.append(f"{act_id}: {e}")
            if len(errors) > 20:
                break

    await db.commit()
    logger.info("Bulk import: inserted=%d, skipped=%d, errors=%d", inserted, skipped, len(errors))
    return {"inserted": inserted, "skipped": skipped, "errors": errors[:20]}
