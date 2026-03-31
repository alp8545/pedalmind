"""On-demand second-by-second ride records from Garmin.

Fetches detailed activity metrics for visualization (power, HR, cadence curves).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.garth_client import garmin_api_call, GarminRateLimitError
from app.models.database import Activity, User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{activity_id}/records")
async def get_ride_records(
    activity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch second-by-second data on-demand from Garmin for detailed visualization."""
    # Verify the activity exists in our DB
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Attivita non trovata")

    try:
        details = await garmin_api_call(
            f"/activity-service/activity/{activity_id}/details"
        )
    except GarminRateLimitError:
        raise HTTPException(
            status_code=429,
            detail="Garmin e' temporaneamente sovraccarico, riprova tra qualche minuto",
        )
    except Exception as e:
        logger.exception("Failed to fetch records for activity %s", activity_id)
        raise HTTPException(status_code=502, detail=f"Errore download dati Garmin: {e}")

    if not details:
        raise HTTPException(status_code=404, detail="Nessun dato dettagliato disponibile")

    # Parse metric descriptors to build named records
    metric_descriptors = details.get("metricDescriptors", [])
    detail_metrics = details.get("activityDetailMetrics", [])

    key_map: dict[int, str] = {}
    for desc in metric_descriptors:
        idx = desc.get("metricsIndex")
        key = desc.get("key", "")
        if idx is not None:
            key_map[idx] = key

    records: list[dict] = []
    for metric in detail_metrics:
        metrics_list = metric.get("metrics", [])
        record: dict = {}
        for idx, key in key_map.items():
            if idx < len(metrics_list):
                record[key] = metrics_list[idx]
        records.append(record)

    return {
        "activity_id": activity_id,
        "count": len(records),
        "metric_keys": list(key_map.values()),
        "records": records,
    }
