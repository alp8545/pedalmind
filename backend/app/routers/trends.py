"""Training trends API — CTL/ATL/TSB + rolling averages."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.trends import compute_trends, compute_rolling_averages, get_trend_summary

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/trends")
async def get_trends(
    days: int = Query(default=90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Return daily CTL/ATL/TSB + rolling averages for the last N days."""
    try:
        points = await compute_trends(db, days=days)
        rolling = await compute_rolling_averages(db, days=days)
    except Exception as e:
        logger.exception("Error computing trends")
        raise HTTPException(status_code=503, detail=f"Errore calcolo trend: {e}")

    # Merge rolling averages into each point (latest only)
    # The rolling averages are period-level, attach to the response root
    return {
        "days": days,
        "points": points,
        **rolling,
    }


@router.get("/trends/summary")
async def get_trends_summary(db: AsyncSession = Depends(get_db)):
    """Return a text summary of current training trends (used by AI chat)."""
    try:
        summary = await get_trend_summary(db)
    except Exception as e:
        logger.exception("Error computing trend summary")
        raise HTTPException(status_code=503, detail=f"Errore calcolo trend: {e}")

    return {"summary": summary}
