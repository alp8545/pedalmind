#!/usr/bin/env python3
"""Bridge: import historical activities from garmin-analyzer into PedalMind.

Reads ~/garmin-analyzer/results/archivio_completo.json, converts each activity
to the RideData contract format, and POSTs to http://localhost:8000/api/rides/upload.

Usage:
    # First register/login to get a JWT token:
    curl -X POST http://localhost:8000/api/auth/register \
        -H 'Content-Type: application/json' \
        -d '{"email":"you@example.com","password":"secret","name":"Alessio"}'

    # Then run the bridge:
    python garmin_sync/bridge.py <JWT_TOKEN>
    python garmin_sync/bridge.py <JWT_TOKEN> --dry-run     # preview without uploading
    python garmin_sync/bridge.py <JWT_TOKEN> --skip 100    # skip first 100 activities
"""

import json
import logging
import math
import os
import sys
import time
import uuid
from datetime import datetime

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bridge")

ARCHIVE_PATH = os.path.expanduser("~/garmin-analyzer/results/archivio_completo.json")
API_BASE = "http://localhost:8000/api"

# Athlete profile from tests/test_data.json
FTP = 265
MAX_HR = 192
RESTING_HR = 57
WEIGHT_KG = 68

# Coggan zone boundaries (% FTP)
POWER_ZONE_BOUNDS = [
    ("z1_recovery",      0.00, 0.55),
    ("z2_endurance",     0.55, 0.75),
    ("z3_tempo",         0.75, 0.90),
    ("z4_threshold",     0.90, 1.05),
    ("z5_vo2max",        1.05, 1.20),
    ("z6_anaerobic",     1.20, 1.50),
    ("z7_neuromuscular", 1.50, 99.0),
]

HR_ZONE_BOUNDS = [
    ("z1_recovery",  0,  60),
    ("z2_endurance", 60, 70),
    ("z3_tempo",     70, 80),
    ("z4_threshold", 80, 90),
    ("z5_vo2max",    90, 100),
]


def _safe(v, as_int: bool = False):
    """Return None for NaN/Inf/missing, otherwise numeric value."""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = float(v.rstrip("%"))
        except (ValueError, AttributeError):
            return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return int(round(v)) if as_int else v


def _parse_pct(s: str | None) -> float:
    """Parse '25.1%' -> 25.1"""
    if not s:
        return 0.0
    try:
        return float(str(s).rstrip("%"))
    except (ValueError, TypeError):
        return 0.0


def _convert_power_zones(zone_dict: dict | None) -> dict[str, int] | None:
    """Convert Italian zone names with % values to contract format with seconds."""
    if not zone_dict:
        return None
    # Map Italian zone names to contract keys
    mapping = {
        "Z1 Recupero": "z1_recovery",
        "Z2 Endurance": "z2_endurance",
        "Z3 Tempo": "z3_tempo",
        "Z4 Soglia": "z4_threshold",
        "Z5 VO2max": "z5_vo2max",
        "Z6 Anaerobica": "z6_anaerobic",
        "Z7 Neuromuscolare": "z7_neuromuscular",
    }
    result: dict[str, int] = {}
    for it_name, contract_name in mapping.items():
        pct = _parse_pct(zone_dict.get(it_name))
        # We don't have absolute seconds from archive, store percentage * 100 as int
        # to keep the schema (integer seconds). The total is relative.
        result[contract_name] = int(round(pct * 100))
    return result


def _convert_hr_zones(zone_dict: dict | None) -> dict[str, int] | None:
    """Convert Italian HR zone names with % values to contract format."""
    if not zone_dict:
        return None
    mapping = {
        "Z1 Recupero": "z1_recovery",
        "Z2 Endurance": "z2_endurance",
        "Z3 Tempo": "z3_tempo",
        "Z4 Soglia": "z4_threshold",
        "Z5 VO2max": "z5_vo2max",
    }
    result: dict[str, int] = {}
    for it_name, contract_name in mapping.items():
        pct = _parse_pct(zone_dict.get(it_name))
        result[contract_name] = int(round(pct * 100))
    return result


def _extract_timestamp(filename: str) -> str:
    """Extract ISO timestamp from filename like '2026-03-13_road_biking_22157493240.fit'."""
    date_part = filename.split("_")[0]
    try:
        dt = datetime.strptime(date_part, "%Y-%m-%d")
        return dt.isoformat() + "Z"
    except ValueError:
        return datetime.now().isoformat() + "Z"


def _extract_garmin_id(filename: str) -> str | None:
    """Extract Garmin activity ID from filename."""
    base = filename.replace(".fit", "")
    parts = base.split("_")
    if parts and parts[-1].isdigit():
        return parts[-1]
    return None


def convert_activity(activity: dict) -> dict:
    """Convert a garmin-analyzer activity dict to RideData contract format."""
    filename = activity.get("file", "unknown.fit")
    timestamp = _extract_timestamp(filename)
    garmin_id = _extract_garmin_id(filename)
    ride_id = str(uuid.uuid5(uuid.NAMESPACE_URL, filename.replace(".fit", "")))

    duration_min = activity.get("durata_min", 0)
    duration_sec = int(round((duration_min or 0) * 60))
    distance_km = _safe(activity.get("distanza_km")) or 0.0

    ride_data: dict = {
        "version": "1.0",
        "ride_id": ride_id,
        "athlete_id": "bridge-import",
        "timestamp": timestamp,
        "summary": {
            "duration_sec": duration_sec,
            "distance_km": round(distance_km, 2),
            "elevation_gain_m": _safe(activity.get("dislivello_positivo"), as_int=True),
            "avg_power_w": _safe(activity.get("potenza_media"), as_int=True),
            "normalized_power_w": _safe(activity.get("potenza_normalizzata"), as_int=True),
            "max_power_w": _safe(activity.get("potenza_max"), as_int=True),
            "intensity_factor": _safe(activity.get("IF")),
            "training_stress_score": _safe(activity.get("TSS")),
            "avg_hr": _safe(activity.get("fc_media"), as_int=True),
            "max_hr": _safe(activity.get("fc_max"), as_int=True),
            "avg_cadence": _safe(activity.get("cadenza_media"), as_int=True),
        },
        "power_curve": {
            "best_5s": _safe(activity.get("best_5s"), as_int=True),
            "best_30s": _safe(activity.get("best_30s"), as_int=True),
            "best_1min": _safe(activity.get("best_1min"), as_int=True),
            "best_5min": _safe(activity.get("best_5min"), as_int=True),
            "best_10min": _safe(activity.get("best_10min"), as_int=True),
            "best_20min": _safe(activity.get("best_20min"), as_int=True),
            "best_60min": _safe(activity.get("best_60min"), as_int=True),
        },
        "zones": {
            "power_zones": _convert_power_zones(activity.get("zone_potenza")),
            "hr_zones": _convert_hr_zones(activity.get("zone_fc")),
        },
        "intervals": [],
        "cardiac_decoupling_pct": _safe(activity.get("decoupling_aerobico_%")),
    }

    if garmin_id:
        ride_data["garmin_activity_id"] = garmin_id

    return ride_data


def main():
    if len(sys.argv) < 2:
        print("Usage: python garmin_sync/bridge.py <JWT_TOKEN> [--dry-run] [--skip N]")
        sys.exit(1)

    token = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    skip = 0
    if "--skip" in sys.argv:
        idx = sys.argv.index("--skip")
        if idx + 1 < len(sys.argv):
            skip = int(sys.argv[idx + 1])

    # Load archive
    if not os.path.exists(ARCHIVE_PATH):
        logger.error("Archive not found: %s", ARCHIVE_PATH)
        sys.exit(1)

    with open(ARCHIVE_PATH) as f:
        archive = json.load(f)

    activities = archive.get("attivita", [])
    total = len(activities)
    logger.info("Loaded %d activities from archive", total)

    if skip > 0:
        activities = activities[skip:]
        logger.info("Skipping first %d, processing %d", skip, len(activities))

    if dry_run:
        logger.info("DRY RUN — converting first 3 activities as preview")
        for act in activities[:3]:
            ride_data = convert_activity(act)
            print(json.dumps(ride_data, indent=2))
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    success = 0
    errors = 0

    for i, act in enumerate(activities):
        filename = act.get("file", "?")
        try:
            ride_data = convert_activity(act)
            resp = requests.post(
                f"{API_BASE}/rides/upload",
                json=ride_data,
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 201:
                success += 1
                if success % 50 == 0:
                    logger.info("Progress: %d/%d uploaded (%.0f%%)", success, len(activities), success / len(activities) * 100)
            else:
                errors += 1
                logger.warning(
                    "[%d/%d] Failed %s: HTTP %d — %s",
                    i + skip + 1, total, filename, resp.status_code, resp.text[:200],
                )
        except Exception as e:
            errors += 1
            logger.error("[%d/%d] Error %s: %s", i + skip + 1, total, filename, e)

        # Rate limit: 50ms between requests
        time.sleep(0.05)

    logger.info("Done. %d uploaded, %d errors out of %d total", success, errors, len(activities))


if __name__ == "__main__":
    main()
