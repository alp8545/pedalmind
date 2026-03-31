"""Ride metrics: decoupling and HR recovery.

Expects records as list[dict] where each dict has at least
'power' (watts, int|None) and 'heartRate' (bpm, int|None) keys.
Records can be sampled at any interval (Garmin often uses ~25-40s intervals,
not true second-by-second).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Minimum valid data points to compute decoupling (need enough for a meaningful split)
MIN_VALID_RECORDS = 20

# Minimum valid data points for HR recovery (need enough to find effort + recovery)
MIN_RECORDS_HR_RECOVERY = 10

# Number of records after peak effort to look for HR recovery
HR_RECOVERY_WINDOW = 5


def compute_decoupling(records: list[dict]) -> float | None:
    """Compute Pw:Hr decoupling percentage.

    Split the ride into two halves. For each half, compute
    avg(power) / avg(HR). Decoupling = ((ratio_h2 - ratio_h1) / ratio_h1) * 100.
    Positive means HR drifted up relative to power (bad aerobic efficiency).

    Returns None if not enough valid records with power+HR data.
    """
    # Filter to records that have both power and HR
    valid = [
        r for r in records
        if r.get("power") is not None
        and r.get("heartRate") is not None
        and r["power"] > 0
        and r["heartRate"] > 0
    ]

    if len(valid) < MIN_VALID_RECORDS:
        return None

    mid = len(valid) // 2
    h1 = valid[:mid]
    h2 = valid[mid:]

    avg_power_h1 = sum(r["power"] for r in h1) / len(h1)
    avg_hr_h1 = sum(r["heartRate"] for r in h1) / len(h1)
    avg_power_h2 = sum(r["power"] for r in h2) / len(h2)
    avg_hr_h2 = sum(r["heartRate"] for r in h2) / len(h2)

    if avg_hr_h1 == 0 or avg_hr_h2 == 0:
        return None

    ratio_h1 = avg_power_h1 / avg_hr_h1
    ratio_h2 = avg_power_h2 / avg_hr_h2

    if ratio_h1 == 0:
        return None

    decoupling = ((ratio_h2 - ratio_h1) / ratio_h1) * 100
    return round(decoupling, 2)


def compute_hr_recovery(records: list[dict]) -> dict | None:
    """Find the hardest effort segment, then measure HR recovery.

    Uses a sliding window (25% of records, min 3) to find the highest avg
    power segment. Then looks at the next few records after that segment
    for HR drop.

    Garmin records are NOT per-second — they're sampled every ~25-40s.
    So "1 record after" is roughly 30s, "2 records after" is roughly 60s.

    Returns:
        {"hr_peak": int, "hr_30s": int, "hr_60s": int,
         "drop_30s": int, "drop_60s": int}
        or None if not enough data.
    """
    # Need power and HR data
    powers = [r.get("power") or 0 for r in records]
    hrs = [r.get("heartRate") or 0 for r in records]

    if len(records) < MIN_RECORDS_HR_RECOVERY:
        return None

    # Window = ~25% of records (effort segment), min 3 records
    window = max(3, len(records) // 4)

    best_avg = -1.0
    best_end = -1

    current_sum = sum(powers[:window])
    if window > 0 and current_sum / window > best_avg:
        best_avg = current_sum / window
        best_end = window

    for i in range(window, len(powers)):
        current_sum += powers[i] - powers[i - window]
        avg = current_sum / window
        if avg > best_avg:
            best_avg = avg
            best_end = i + 1

    if best_end < 0 or best_avg <= 0:
        return None

    # HR at the end of the hardest segment
    hr_peak = hrs[best_end - 1] if best_end - 1 < len(hrs) else 0
    if hr_peak <= 0:
        return None

    # Look for HR recovery in the records AFTER the effort
    # Each record is ~30-40s apart, so +1 record ≈ 30s, +2 records ≈ 60s
    hr_30s = hrs[best_end] if best_end < len(hrs) else None
    hr_60s = hrs[best_end + 1] if best_end + 1 < len(hrs) else None

    if hr_30s is None and hr_60s is None:
        return None

    result: dict = {"hr_peak": hr_peak}
    if hr_30s is not None and hr_30s > 0:
        result["hr_30s"] = hr_30s
        result["drop_30s"] = hr_peak - hr_30s
    if hr_60s is not None and hr_60s > 0:
        result["hr_60s"] = hr_60s
        result["drop_60s"] = hr_peak - hr_60s

    if "drop_30s" not in result and "drop_60s" not in result:
        return None

    return result
