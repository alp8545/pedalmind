import json
import logging
import traceback
from datetime import datetime, timezone

import anthropic
from anthropic import APIError

from ai_engine.prompts import RIDE_ANALYSIS_SYSTEM, RIDE_ANALYSIS_USER, CHAT_SYSTEM, CHAT_CONTEXT_TEMPLATE

logger = logging.getLogger("ai_engine")

RIDE_TYPES = [
    "endurance", "tempo", "threshold", "vo2max",
    "race", "recovery", "mixed",
]

# Coggan power zones based on FTP
COGGAN_ZONE_PCTS = [
    ("Z1 Recovery", 0, 0.55),
    ("Z2 Endurance", 0.55, 0.75),
    ("Z3 Tempo", 0.75, 0.90),
    ("Z4 Threshold", 0.90, 1.05),
    ("Z5 VO2max", 1.05, 1.20),
    ("Z6 Anaerobic", 1.20, 1.50),
    ("Z7 Neuromuscular", 1.50, 999),
]


def compute_power_zones(ftp: int) -> str:
    lines = []
    for name, lo_pct, hi_pct in COGGAN_ZONE_PCTS:
        lo = int(ftp * lo_pct)
        hi = int(ftp * hi_pct) if hi_pct < 100 else "+"
        lines.append(f"{name}: {lo}-{hi}W" if isinstance(hi, int) else f"{name}: >{lo}W")
    return "\n".join(lines)


def compute_cardiac_analysis(splits_data: dict | None, raw_data: dict | None,
                              avg_power: int | None, avg_hr: int | None,
                              duration_secs: float | None) -> dict:
    """Pre-compute cardiac decoupling and HR recovery from lap/split data."""
    result = {
        "decoupling_pct": None,
        "hr_recovery_blocks": [],
        "first_half": {},
        "second_half": {},
    }

    laps = []
    if splits_data and isinstance(splits_data, dict):
        laps = splits_data.get("lapDTOs", [])

    # Compute decoupling from laps
    if laps and len(laps) >= 2:
        mid = len(laps) // 2
        first_half = laps[:mid]
        second_half = laps[mid:]

        def half_stats(half):
            total_dur = sum(l.get("duration", 0) for l in half)
            if total_dur == 0:
                return None, None
            w_power = sum((l.get("averagePower") or 0) * (l.get("duration") or 0) for l in half) / total_dur
            w_hr = sum((l.get("averageHR") or 0) * (l.get("duration") or 0) for l in half) / total_dur
            return w_power, w_hr

        p1, hr1 = half_stats(first_half)
        p2, hr2 = half_stats(second_half)

        if p1 and hr1 and hr1 > 0 and p2 and hr2 and hr2 > 0:
            eff1 = p1 / hr1
            eff2 = p2 / hr2
            decoupling = ((eff1 - eff2) / eff1) * 100 if eff1 > 0 else 0
            result["decoupling_pct"] = round(decoupling, 1)
            result["first_half"] = {"avg_power": round(p1), "avg_hr": round(hr1), "efficiency": round(eff1, 3)}
            result["second_half"] = {"avg_power": round(p2), "avg_hr": round(hr2), "efficiency": round(eff2, 3)}

    # Compute HR recovery blocks from laps with intensity changes
    if laps and len(laps) >= 3:
        blocks = []
        for i in range(1, len(laps) - 1):
            curr = laps[i]
            nxt = laps[i + 1]
            curr_power = curr.get("averagePower") or 0
            nxt_power = nxt.get("averagePower") or 0
            curr_hr = curr.get("averageHR") or 0
            nxt_hr = nxt.get("averageHR") or 0
            # Detect work→recovery transition (power drop >40%)
            if curr_power > 0 and nxt_power > 0 and nxt_power < curr_power * 0.6 and curr_hr > 100:
                hr_drop = curr_hr - nxt_hr
                if hr_drop < 10:
                    assessment = "molto lento"
                elif hr_drop < 20:
                    assessment = "lento"
                elif hr_drop < 30:
                    assessment = "buono"
                else:
                    assessment = "eccellente"
                blocks.append({
                    "block_number": len(blocks) + 1,
                    "work_avg_power": round(curr_power),
                    "work_avg_hr": round(curr_hr),
                    "recovery_duration_secs": round(nxt.get("duration", 0)),
                    "hr_at_recovery_start": round(curr_hr),
                    "hr_at_recovery_end": round(nxt_hr),
                    "hr_drop": round(hr_drop),
                    "hr_drop_assessment": assessment,
                })
        result["hr_recovery_blocks"] = blocks[:5]  # max 5 blocks

    return result


def _build_recent_summary(recent_rides: list[dict]) -> str:
    if not recent_rides:
        return "Nessuna uscita recente."
    lines: list[str] = []
    for r in recent_rides:
        summary = r.get("summary", {})
        lines.append(
            f"- {r.get('timestamp', '?')}: "
            f"{summary.get('distance_km', 0):.1f} km, "
            f"{summary.get('duration_sec', 0) // 60} min, "
            f"avg {summary.get('avg_power_w', '?')}W, "
            f"NP {summary.get('normalized_power_w', '?')}W, "
            f"TSS {summary.get('training_stress_score', '?')}"
        )
    return "\n".join(lines)


async def analyze_ride(
    ride_data: dict,
    athlete_profile: dict,
    recent_rides: list[dict],
    model: str = "claude-haiku-4-5-20251001",
    api_key: str = "",
    splits_data: dict | None = None,
    raw_data: dict | None = None,
    avg_power: int | None = None,
    avg_hr: int | None = None,
    duration_secs: float | None = None,
) -> dict:
    """Call Anthropic API to analyze a ride. Returns a RideAnalysis dict."""
    logger.info("analyze_ride: starting, model=%s, api_key_set=%s", model, bool(api_key))

    ftp = athlete_profile.get("ftp_watts", 265)
    power_zones = compute_power_zones(ftp)
    cardiac = compute_cardiac_analysis(splits_data, raw_data, avg_power, avg_hr, duration_secs)

    logger.info("analyze_ride: decoupling_pct=%s, recovery_blocks=%d",
                cardiac.get("decoupling_pct"), len(cardiac.get("hr_recovery_blocks", [])))

    user_prompt = RIDE_ANALYSIS_USER.format(
        athlete_profile_json=json.dumps(athlete_profile, default=str),
        ride_data_json=json.dumps(ride_data, default=str),
        recent_rides_summary=_build_recent_summary(recent_rides),
        power_zones=power_zones,
        cardiac_analysis_json=json.dumps(cardiac, default=str, indent=2),
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        logger.info("analyze_ride: calling Anthropic API...")
        response = await client.messages.create(
            model=model,
            max_tokens=3000,
            system=RIDE_ANALYSIS_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        logger.info("analyze_ride: API response received, tokens in=%d out=%d",
                     response.usage.input_tokens, response.usage.output_tokens)
    except APIError as e:
        logger.error("analyze_ride: Anthropic API error: type=%s status=%s message=%s",
                     type(e).__name__, getattr(e, 'status_code', '?'), e)
        raise
    except Exception as e:
        logger.error("analyze_ride: unexpected error: %s\n%s", e, traceback.format_exc())
        raise

    raw_text = response.content[0].text
    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        if raw_text.endswith("```"):
            raw_text = raw_text[: raw_text.rfind("```")]
    raw_text = raw_text.strip()

    try:
        analysis = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error("analyze_ride: failed to parse JSON: %s\nraw_text: %s", e, raw_text[:500])
        raise

    # Ensure required fields
    analysis["version"] = "1.0"
    analysis["ride_id"] = ride_data.get("ride_id", "")
    analysis["model_used"] = model
    analysis["generated_at"] = datetime.now(timezone.utc).isoformat()
    analysis["tokens_input"] = response.usage.input_tokens
    analysis["tokens_output"] = response.usage.output_tokens

    # Inject pre-computed cardiac data
    if "cardiac_analysis" not in analysis:
        analysis["cardiac_analysis"] = {}
    if cardiac["decoupling_pct"] is not None:
        analysis["cardiac_analysis"]["decoupling_pct"] = cardiac["decoupling_pct"]
    if cardiac["hr_recovery_blocks"]:
        analysis["cardiac_analysis"]["hr_recovery_blocks"] = cardiac["hr_recovery_blocks"]

    if analysis.get("ride_type") not in RIDE_TYPES:
        analysis["ride_type"] = "mixed"

    logger.info("analyze_ride: complete, ride_type=%s, scores=%s", analysis.get("ride_type"), analysis.get("scores"))
    return analysis


async def chat_response(
    user_message: str,
    athlete_profile: dict,
    training_summary_30d: str,
    recent_rides_with_analysis: str,
    conversation_history: list[dict],
    model: str = "claude-sonnet-4-6",
    api_key: str = "",
    latest_activity: str = "",
    training_load: str = "",
) -> tuple[str, int | None]:
    """Call Anthropic chat API. Returns (response_text, tokens_used)."""
    logger.info("chat_response: starting, model=%s, api_key_set=%s, history_len=%d",
                model, bool(api_key), len(conversation_history))

    context = CHAT_CONTEXT_TEMPLATE.format(
        athlete_profile_json=json.dumps(athlete_profile, default=str),
        training_summary_30d=training_summary_30d,
        recent_rides_with_analysis=recent_rides_with_analysis,
        latest_activity=latest_activity or "Nessuna attivita recente.",
        training_load=training_load or "Non disponibile.",
    )

    messages: list[dict] = [{"role": "user", "content": context}]
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    # Merge consecutive same-role messages
    merged: list[dict] = []
    for m in messages:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n\n" + m["content"]
        else:
            merged.append(m)

    logger.info("chat_response: sending %d messages to Anthropic", len(merged))

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=CHAT_SYSTEM,
            messages=merged,
        )
        logger.info("chat_response: API response received, tokens in=%d out=%d",
                     response.usage.input_tokens, response.usage.output_tokens)
    except APIError as e:
        logger.error("chat_response: Anthropic API error: type=%s status=%s message=%s",
                     type(e).__name__, getattr(e, 'status_code', '?'), e)
        raise
    except Exception as e:
        logger.error("chat_response: unexpected error: %s\n%s", e, traceback.format_exc())
        raise

    text = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return text, tokens


async def test_api_key(api_key: str) -> dict:
    """Minimal test call to verify API key works."""
    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say OK"}],
        )
        return {"status": "ok", "response": response.content[0].text, "tokens": response.usage.input_tokens + response.usage.output_tokens}
    except APIError as e:
        return {"status": "error", "type": type(e).__name__, "status_code": getattr(e, 'status_code', None), "message": str(e)}
    except Exception as e:
        return {"status": "error", "type": type(e).__name__, "message": str(e)}
