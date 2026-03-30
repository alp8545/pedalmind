"""Training trend analysis using Coggan EWMA (CTL/ATL/TSB).

CTL (Chronic Training Load / Fitness): 42-day exponentially weighted moving average of daily TSS
ATL (Acute Training Load / Fatigue):    7-day EWMA of daily TSS
TSB (Training Stress Balance / Form):   CTL - ATL

Only cycling activities with valid TSS contribute. Non-cycling and null-TSS
activities are treated as rest days (daily_tss=0).
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Activity

logger = logging.getLogger(__name__)

# Coggan EWMA time constants
CTL_DAYS = 42
ATL_DAYS = 7

# Cycling sport keys from Garmin
CYCLING_SPORTS = {"cycling", "road_biking", "mountain_biking", "gravel_cycling",
                  "indoor_cycling", "virtual_ride", "recumbent_cycling",
                  "track_cycling", "e_bike_mountain", "e_bike_road",
                  "bike", "road", "mountain", "gravel"}

# Form indicator thresholds (TSB ranges)
FORM_THRESHOLDS = [
    (15, "Peaked"),
    (5, "Fresh"),
    (-10, "Building"),
    (-25, "Fatigued"),
]
FORM_OVERREACHING = "Overreaching"


def get_form_indicator(tsb: float) -> str:
    """Map TSB value to a form indicator label."""
    for threshold, label in FORM_THRESHOLDS:
        if tsb >= threshold:
            return label
    return FORM_OVERREACHING


async def compute_trends(db: AsyncSession, days: int = 90) -> list[dict]:
    """Compute daily CTL/ATL/TSB from all cycling activities.

    Computes EWMA over the FULL activity history (not just the requested window)
    to ensure warm values. Returns only the last `days` of data points.
    """
    # Fetch all cycling activities with TSS, ordered chronologically
    result = await db.execute(
        select(Activity)
        .where(
            Activity.tss.isnot(None),
            Activity.start_time.isnot(None),
            Activity.sport.in_(CYCLING_SPORTS),
        )
        .order_by(Activity.start_time.asc())
    )
    activities = result.scalars().all()

    if not activities:
        return []

    # Group TSS by calendar date
    daily_tss: dict[date, float] = {}
    for a in activities:
        d = a.start_time.date()
        daily_tss[d] = daily_tss.get(d, 0.0) + a.tss

    # Build continuous date range from first activity to today
    first_date = min(daily_tss.keys())
    today = date.today()
    total_days = (today - first_date).days + 1

    # Compute EWMA: today = yesterday * (1 - 1/TC) + daily_tss * (1/TC)
    ctl = 0.0
    atl = 0.0
    ctl_decay = 1.0 - 1.0 / CTL_DAYS
    ctl_gain = 1.0 / CTL_DAYS
    atl_decay = 1.0 - 1.0 / ATL_DAYS
    atl_gain = 1.0 / ATL_DAYS

    all_points: list[dict] = []

    for i in range(total_days):
        d = first_date + timedelta(days=i)
        tss = daily_tss.get(d, 0.0)

        ctl = ctl * ctl_decay + tss * ctl_gain
        atl = atl * atl_decay + tss * atl_gain
        tsb = ctl - atl

        all_points.append({
            "date": d.isoformat(),
            "ctl": round(ctl, 1),
            "atl": round(atl, 1),
            "tsb": round(tsb, 1),
            "form": get_form_indicator(tsb),
            "daily_tss": round(tss, 1),
        })

    # Return only the last `days` points
    return all_points[-days:]


async def compute_rolling_averages(db: AsyncSession, days: int = 90) -> dict[str, dict]:
    """Compute 7-day and 30-day rolling averages for key metrics.

    Returns averages for the most recent period. Days with no rides count as 0.
    """
    today = date.today()
    cutoff_30 = today - timedelta(days=30)
    cutoff_7 = today - timedelta(days=7)

    result = await db.execute(
        select(Activity)
        .where(
            Activity.start_time.isnot(None),
            Activity.sport.in_(CYCLING_SPORTS),
        )
        .order_by(Activity.start_time.asc())
    )
    activities = result.scalars().all()

    def _avg_for_period(cutoff: date, window_days: int) -> dict:
        period_activities = [
            a for a in activities
            if a.start_time and a.start_time.date() > cutoff
        ]
        count = len(period_activities)
        if count == 0:
            return {"distance_km": 0, "duration_h": 0, "tss": 0, "avg_power": 0, "avg_hr": 0}

        total_distance = sum((a.distance_m or 0) for a in period_activities)
        total_duration = sum((a.duration_secs or 0) for a in period_activities)
        total_tss = sum((a.tss or 0) for a in period_activities)
        powers = [a.avg_power for a in period_activities if a.avg_power]
        hrs = [a.avg_hr for a in period_activities if a.avg_hr]

        return {
            "distance_km": round(total_distance / 1000 / window_days * 7, 1),  # weekly avg
            "duration_h": round(total_duration / 3600 / window_days * 7, 1),    # weekly avg
            "tss": round(total_tss / window_days * 7, 0),                       # weekly avg
            "avg_power": round(sum(powers) / len(powers)) if powers else 0,
            "avg_hr": round(sum(hrs) / len(hrs)) if hrs else 0,
        }

    return {
        "rolling_7d": _avg_for_period(cutoff_7, 7),
        "rolling_30d": _avg_for_period(cutoff_30, 30),
    }


async def get_trend_summary(db: AsyncSession) -> str:
    """Generate a text summary of current training trends for AI chat context.

    Returns a template-based string describing CTL, ATL, TSB, and form status.
    """
    points = await compute_trends(db, days=14)
    if not points:
        return "Non abbastanza dati per calcolare i trend di allenamento."

    latest = points[-1]
    ctl = latest["ctl"]
    atl = latest["atl"]
    tsb = latest["tsb"]
    form = latest["form"]

    # CTL trend over last 7 days
    if len(points) >= 7:
        ctl_7d_ago = points[-7]["ctl"]
        ctl_delta = round(ctl - ctl_7d_ago, 1)
        ctl_direction = "in crescita" if ctl_delta > 1 else "in calo" if ctl_delta < -1 else "stabile"
    else:
        ctl_delta = 0
        ctl_direction = "non abbastanza dati"

    # Rolling averages
    rolling = await compute_rolling_averages(db)
    weekly_tss = rolling["rolling_7d"]["tss"]

    return (
        f"CTL (fitness): {ctl} ({ctl_direction}, {ctl_delta:+.1f} ultimi 7gg) | "
        f"ATL (fatica): {atl} | TSB (forma): {tsb} ({form})\n"
        f"TSS settimanale: {weekly_tss} | "
        f"Potenza media: {rolling['rolling_7d']['avg_power']}W | "
        f"FC media: {rolling['rolling_7d']['avg_hr']}bpm"
    )
