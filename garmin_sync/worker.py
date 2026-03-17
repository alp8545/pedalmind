"""Garmin sync worker: FIT file parsing and activity download.

Reuses logic from ~/garmin-analyzer/garmin_auto.py, adapted to produce
RideData dicts matching contracts/ride_data.json.
"""

import asyncio
import logging
import math
import os
import uuid
import zipfile
from datetime import datetime, timezone

import pandas as pd
from fitparse import FitFile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("garmin_sync")

POLL_INTERVAL_SEC = 1800

# Coggan 7-zone power boundaries (% of FTP)
POWER_ZONE_BOUNDS = [
    ("z1_recovery",      0.00, 0.55),
    ("z2_endurance",     0.55, 0.75),
    ("z3_tempo",         0.75, 0.90),
    ("z4_threshold",     0.90, 1.05),
    ("z5_vo2max",        1.05, 1.20),
    ("z6_anaerobic",     1.20, 1.50),
    ("z7_neuromuscular", 1.50, 99.0),
]

# 5-zone HR boundaries (% of HR reserve)
HR_ZONE_BOUNDS = [
    ("z1_recovery",  0,  60),
    ("z2_endurance", 60, 70),
    ("z3_tempo",     70, 80),
    ("z4_threshold", 80, 90),
    ("z5_vo2max",    90, 100),
]

# Power curve durations to compute best efforts for
POWER_CURVE_WINDOWS = {
    "best_5s": 5,
    "best_30s": 30,
    "best_1min": 60,
    "best_5min": 300,
    "best_10min": 600,
    "best_20min": 1200,
    "best_60min": 3600,
}


def _safe_int(v) -> int | None:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return int(round(v))


def _safe_float(v, decimals: int = 2) -> float | None:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), decimals)


def _power_zone(watts: float, ftp: int) -> str:
    ratio = watts / ftp if ftp > 0 else 0
    for name, lo, hi in POWER_ZONE_BOUNDS:
        if lo <= ratio < hi:
            return name
    return "z7_neuromuscular"


def _hr_zone(hr: float, max_hr: int, resting_hr: int = 0) -> str:
    reserve = max_hr - resting_hr
    pct = ((hr - resting_hr) / reserve * 100) if reserve > 0 else 0
    for name, lo, hi in HR_ZONE_BOUNDS:
        if lo <= pct < hi:
            return name
    return "z5_vo2max"


def parse_fit_file(
    fit_path: str,
    ftp: int,
    max_hr: int,
    resting_hr: int = 0,
    weight_kg: float = 70.0,
    athlete_id: str = "",
    garmin_activity_id: str | None = None,
) -> dict:
    """Parse a .FIT file into a RideData contract dict.

    Key formulas:
      NP = 4th root of mean of (30s rolling avg power)^4
      IF = NP / FTP
      TSS = (duration_sec * NP * IF) / (FTP * 3600) * 100
      VI = NP / avg_power
      Decoupling = ((P1/HR1) - (P2/HR2)) / (P1/HR1) * 100
    """
    fit = FitFile(fit_path)
    records: list[dict] = []
    for record in fit.get_messages("record"):
        row: dict = {}
        for field in record.fields:
            val = field.value
            if isinstance(val, datetime):
                val = val.isoformat()
            row[field.name] = val
        records.append(row)

    if not records:
        logger.warning("No records in FIT file: %s", fit_path)
        return {}

    df = pd.DataFrame(records)

    # --- Timestamp and duration ---
    ride_timestamp: str | None = None
    duration_sec = 0
    if "timestamp" in df.columns:
        df["_ts"] = pd.to_datetime(df["timestamp"])
        ride_timestamp = str(df["_ts"].iloc[0].isoformat())
        duration_sec = int((df["_ts"].max() - df["_ts"].min()).total_seconds())

    if ride_timestamp is None:
        ride_timestamp = datetime.now(timezone.utc).isoformat()

    # --- Distance ---
    distance_km = 0.0
    if "distance" in df.columns:
        d = df["distance"].max()
        if d and not math.isnan(d):
            distance_km = round(d / 1000, 2)

    # --- Elevation ---
    elevation_gain = None
    alt_col = "enhanced_altitude" if "enhanced_altitude" in df.columns else "altitude" if "altitude" in df.columns else None
    if alt_col:
        alt = df[alt_col].dropna().astype(float)
        if len(alt) > 0:
            diff = alt.diff()
            gain = diff[diff > 0].sum()
            elevation_gain = _safe_int(gain)

    # --- Power metrics ---
    avg_power = None
    np_value = None
    max_power = None
    intensity_factor = None
    tss = None
    vi = None
    power_zones: dict[str, int] | None = None
    power_curve: dict[str, int | None] = {}
    intervals: list[dict] = []

    if "power" in df.columns:
        pwr = df["power"].dropna().astype(float)
        if len(pwr) > 0:
            avg_power = _safe_int(pwr.mean())
            max_power = _safe_int(pwr.max())

            # NP: 30-second rolling average, raised to 4th power
            rolling_30 = pwr.rolling(30, min_periods=1).mean()
            np_value = _safe_int((rolling_30 ** 4).mean() ** 0.25)

            if np_value and ftp > 0:
                intensity_factor = _safe_float(np_value / ftp)
                if duration_sec > 0:
                    tss = _safe_float(
                        (duration_sec * np_value * (np_value / ftp)) / (ftp * 3600) * 100,
                        1,
                    )
                vi = _safe_float(np_value / pwr.mean())

            # Coggan 7-zone distribution (seconds in each zone)
            zone_counts: dict[str, int] = {name: 0 for name, _, _ in POWER_ZONE_BOUNDS}
            for w in pwr:
                z = _power_zone(w, ftp)
                zone_counts[z] += 1
            power_zones = zone_counts

            # Power curve best efforts
            for label, window in POWER_CURVE_WINDOWS.items():
                if len(pwr) >= window:
                    best = pwr.rolling(window).mean().max()
                    power_curve[label] = _safe_int(best)
                else:
                    power_curve[label] = None

            # Auto-detect intervals: contiguous segments above Z4 threshold (105% FTP)
            z4_threshold = ftp * 1.05
            in_interval = False
            interval_start = 0
            interval_powers: list[float] = []
            interval_hrs: list[float] = []
            interval_cads: list[float] = []

            for i, w in enumerate(pwr):
                if w >= z4_threshold:
                    if not in_interval:
                        in_interval = True
                        interval_start = i
                        interval_powers = []
                        interval_hrs = []
                        interval_cads = []
                    interval_powers.append(w)
                    if "heart_rate" in df.columns and pd.notna(df["heart_rate"].iloc[i]):
                        interval_hrs.append(float(df["heart_rate"].iloc[i]))
                    if "cadence" in df.columns and pd.notna(df["cadence"].iloc[i]):
                        interval_cads.append(float(df["cadence"].iloc[i]))
                else:
                    if in_interval and len(interval_powers) >= 10:
                        avg_int_power = int(round(sum(interval_powers) / len(interval_powers)))
                        intervals.append({
                            "start_sec": interval_start,
                            "duration_sec": len(interval_powers),
                            "avg_power_w": avg_int_power,
                            "max_power_w": int(max(interval_powers)),
                            "avg_hr": int(round(sum(interval_hrs) / len(interval_hrs))) if interval_hrs else None,
                            "avg_cadence": int(round(sum(interval_cads) / len(interval_cads))) if interval_cads else None,
                            "zone": _power_zone(avg_int_power, ftp).upper(),
                        })
                    in_interval = False

            # Catch interval that runs to end of file
            if in_interval and len(interval_powers) >= 10:
                avg_int_power = int(round(sum(interval_powers) / len(interval_powers)))
                intervals.append({
                    "start_sec": interval_start,
                    "duration_sec": len(interval_powers),
                    "avg_power_w": avg_int_power,
                    "max_power_w": int(max(interval_powers)),
                    "avg_hr": int(round(sum(interval_hrs) / len(interval_hrs))) if interval_hrs else None,
                    "avg_cadence": int(round(sum(interval_cads) / len(interval_cads))) if interval_cads else None,
                    "zone": _power_zone(avg_int_power, ftp).upper(),
                })

    # --- HR metrics ---
    avg_hr = None
    max_hr_val = None
    hr_zones: dict[str, int] | None = None

    if "heart_rate" in df.columns:
        hr = df["heart_rate"].dropna().astype(float)
        if len(hr) > 0:
            avg_hr = _safe_int(hr.mean())
            max_hr_val = _safe_int(hr.max())

            # 5-zone HR distribution (seconds in each zone)
            zone_counts_hr: dict[str, int] = {name: 0 for name, _, _ in HR_ZONE_BOUNDS}
            for h in hr:
                z = _hr_zone(h, max_hr, resting_hr)
                zone_counts_hr[z] += 1
            hr_zones = zone_counts_hr

    # --- Cadence ---
    avg_cadence = None
    if "cadence" in df.columns:
        cad = df["cadence"].dropna().astype(float)
        if len(cad) > 0:
            avg_cadence = _safe_int(cad.mean())

    # --- Cardiac decoupling ---
    cardiac_decoupling: float | None = None
    if "power" in df.columns and "heart_rate" in df.columns:
        mid = len(df) // 2
        if mid > 0:
            pw1 = df["power"].iloc[:mid].dropna().astype(float).mean()
            pw2 = df["power"].iloc[mid:].dropna().astype(float).mean()
            hr1 = df["heart_rate"].iloc[:mid].dropna().astype(float).mean()
            hr2 = df["heart_rate"].iloc[mid:].dropna().astype(float).mean()
            if hr1 > 0 and hr2 > 0 and pw1 > 0 and pw2 > 0:
                ef1 = pw1 / hr1
                ef2 = pw2 / hr2
                cardiac_decoupling = _safe_float(((ef1 - ef2) / ef1) * 100, 2)

    # --- Build ride_id from filename or generate ---
    basename = os.path.basename(fit_path).replace(".fit", "")
    ride_id = str(uuid.uuid5(uuid.NAMESPACE_URL, basename))

    # --- Extract garmin_activity_id from filename if not provided ---
    if garmin_activity_id is None:
        parts = basename.split("_")
        if len(parts) >= 3 and parts[-1].isdigit():
            garmin_activity_id = parts[-1]

    # --- Assemble RideData contract ---
    ride_data: dict = {
        "version": "1.0",
        "ride_id": ride_id,
        "athlete_id": athlete_id,
        "timestamp": ride_timestamp,
        "summary": {
            "duration_sec": duration_sec,
            "distance_km": distance_km,
            "elevation_gain_m": elevation_gain,
            "avg_power_w": avg_power,
            "normalized_power_w": np_value,
            "max_power_w": max_power,
            "intensity_factor": intensity_factor,
            "training_stress_score": tss,
            "avg_hr": avg_hr,
            "max_hr": max_hr_val,
            "avg_cadence": avg_cadence,
        },
        "power_curve": power_curve if power_curve else {
            "best_5s": None, "best_30s": None, "best_1min": None,
            "best_5min": None, "best_10min": None, "best_20min": None,
            "best_60min": None,
        },
        "zones": {
            "power_zones": power_zones,
            "hr_zones": hr_zones,
        },
        "intervals": intervals,
        "cardiac_decoupling_pct": cardiac_decoupling,
    }

    if garmin_activity_id:
        ride_data["garmin_activity_id"] = garmin_activity_id

    return ride_data


def download_activities(
    email: str,
    password: str,
    days: int = 7,
    fit_dir: str = "/tmp/pedalmind_fits",
) -> list[str]:
    """Download recent activities from Garmin Connect. Returns list of FIT file paths."""
    from garminconnect import Garmin

    os.makedirs(fit_dir, exist_ok=True)
    client = Garmin(email, password)
    client.login()
    logger.info("Logged in to Garmin Connect")

    activities = client.get_activities(0, 50)
    cutoff = (datetime.now() - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
    downloaded: list[str] = []

    for act in activities:
        date_str = act.get("startTimeLocal", "")[:10]
        if date_str < cutoff:
            continue

        aid = act["activityId"]
        sport = act.get("activityType", {}).get("typeKey", "unknown")
        fit_filename = f"{date_str}_{sport}_{aid}.fit"
        fit_path = os.path.join(fit_dir, fit_filename)

        if os.path.exists(fit_path):
            downloaded.append(fit_path)
            continue

        logger.info("Downloading: %s (%s)", act.get("activityName", ""), date_str)
        zip_data = client.download_activity(aid, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)
        zip_path = fit_path + ".zip"

        with open(zip_path, "wb") as f:
            f.write(zip_data)

        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                fit_names = [n for n in z.namelist() if n.endswith(".fit")]
                if fit_names:
                    with open(fit_path, "wb") as f:
                        f.write(z.read(fit_names[0]))
            os.remove(zip_path)
        except zipfile.BadZipFile:
            os.rename(zip_path, fit_path)

        downloaded.append(fit_path)

    logger.info("Downloaded %d activities", len(downloaded))
    return downloaded


async def sync_user(user_id: str, garmin_token: str, garmin_refresh: str) -> list[dict]:
    # TODO: implement OAuth-based Garmin API sync
    logger.info("Syncing user %s — OAuth not yet implemented", user_id)
    return []


async def worker_loop():
    logger.info("Garmin sync worker started")
    while True:
        try:
            logger.info("Poll cycle — no users yet")
        except Exception as e:
            logger.error("Sync error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(worker_loop())
