"""Second-by-second ride metrics: decoupling and HR recovery.

Expects records as list[dict] where each dict has at least
'power' (watts, int|None) and 'heartRate' (bpm, int|None) keys,
one entry per second.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Minimum ride length in seconds (20 min) to compute decoupling
MIN_DURATION_SECS = 20 * 60

# Window for finding hardest effort (5 min)
HARD_EFFORT_WINDOW = 5 * 60


def compute_decoupling(records: list[dict]) -> float | None:
    """Compute Pw:Hr decoupling percentage.

    Split the ride into two halves. For each half, compute
    avg(power) / avg(HR). Decoupling = ((ratio_h2 - ratio_h1) / ratio_h1) * 100.
    Positive means HR drifted up relative to power (bad aerobic efficiency).

    Returns None if ride is < 20 min or lacks power+HR data.
    """
    if len(records) < MIN_DURATION_SECS:
        return None

    # Filter to records that have both power and HR
    valid = [
        r for r in records
        if r.get("power") is not None
        and r.get("heartRate") is not None
        and r["power"] > 0
        and r["heartRate"] > 0
    ]

    if len(valid) < MIN_DURATION_SECS:
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
    """Find the highest 5-min avg power segment, then measure HR recovery.

    From the end of that segment, measure HR drop at +30s and +60s.

    Returns:
        {"hr_peak": int, "hr_30s": int, "hr_60s": int,
         "drop_30s": int, "drop_60s": int}
        or None if not enough data.
    """
    if len(records) < HARD_EFFORT_WINDOW + 60:
        return None

    # Build power values list (0 for missing)
    powers = [r.get("power") or 0 for r in records]
    hrs = [r.get("heartRate") or 0 for r in records]

    # Sliding window to find highest 5-min avg power segment
    window = HARD_EFFORT_WINDOW
    best_avg = -1.0
    best_end = -1

    # Running sum for efficiency
    current_sum = sum(powers[:window])
    if current_sum / window > best_avg:
        best_avg = current_sum / window
        best_end = window

    for i in range(window, len(powers)):
        current_sum += powers[i] - powers[i - window]
        avg = current_sum / window
        if avg > best_avg:
            best_avg = avg
            best_end = i + 1  # exclusive end index

    if best_end < 0 or best_avg <= 0:
        return None

    # HR at the end of the hardest segment
    hr_peak = hrs[best_end - 1] if best_end - 1 < len(hrs) else 0
    if hr_peak <= 0:
        return None

    # Check we have enough data after the segment
    if best_end + 60 > len(records):
        # Try with what we have
        hr_30s = hrs[best_end + 29] if best_end + 30 <= len(hrs) else None
        hr_60s = hrs[best_end + 59] if best_end + 60 <= len(hrs) else None
    else:
        hr_30s = hrs[best_end + 29]
        hr_60s = hrs[best_end + 59]

    if hr_30s is None and hr_60s is None:
        return None

    result: dict = {"hr_peak": hr_peak}
    if hr_30s is not None and hr_30s > 0:
        result["hr_30s"] = hr_30s
        result["drop_30s"] = hr_peak - hr_30s
    if hr_60s is not None and hr_60s > 0:
        result["hr_60s"] = hr_60s
        result["drop_60s"] = hr_peak - hr_60s

    # Must have at least one valid recovery measurement
    if "drop_30s" not in result and "drop_60s" not in result:
        return None

    return result
