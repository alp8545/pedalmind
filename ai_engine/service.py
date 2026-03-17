import json
import logging
from datetime import datetime, timezone

import anthropic

from ai_engine.prompts import RIDE_ANALYSIS_SYSTEM, RIDE_ANALYSIS_USER, CHAT_SYSTEM, CHAT_CONTEXT_TEMPLATE

logger = logging.getLogger(__name__)

RIDE_TYPES = [
    "endurance", "tempo", "threshold", "vo2max_intervals",
    "sprint_intervals", "mixed", "race", "recovery", "group_ride", "commute",
]


def _build_recent_summary(recent_rides: list[dict]) -> str:
    if not recent_rides:
        return "No recent rides available."
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
) -> dict:
    """Call Anthropic API to analyze a ride. Returns a RideAnalysis dict."""
    preferred_language = athlete_profile.get("preferred_language", "en")

    user_prompt = RIDE_ANALYSIS_USER.format(
        athlete_profile_json=json.dumps(athlete_profile, default=str),
        ride_data_json=json.dumps(ride_data, default=str),
        recent_rides_summary=_build_recent_summary(recent_rides),
        preferred_language=preferred_language,
    )

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=RIDE_ANALYSIS_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text
    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        if raw_text.endswith("```"):
            raw_text = raw_text[: raw_text.rfind("```")]
    analysis = json.loads(raw_text)

    # Ensure required contract fields
    analysis["version"] = "1.0"
    analysis["ride_id"] = ride_data.get("ride_id", "")
    analysis["model_used"] = model
    analysis["generated_at"] = datetime.now(timezone.utc).isoformat()
    analysis["tokens_input"] = response.usage.input_tokens
    analysis["tokens_output"] = response.usage.output_tokens

    if analysis.get("ride_type_detected") not in RIDE_TYPES:
        analysis["ride_type_detected"] = "mixed"

    return analysis


async def chat_response(
    user_message: str,
    athlete_profile: dict,
    training_summary_30d: str,
    recent_rides_with_analysis: str,
    conversation_history: list[dict],
    model: str = "claude-sonnet-4-6",
    api_key: str = "",
) -> tuple[str, int | None]:
    """Call Anthropic chat API. Returns (response_text, tokens_used)."""
    context = CHAT_CONTEXT_TEMPLATE.format(
        athlete_profile_json=json.dumps(athlete_profile, default=str),
        training_summary_30d=training_summary_30d,
        recent_rides_with_analysis=recent_rides_with_analysis,
        conversation_history=json.dumps(conversation_history, default=str),
    )

    messages: list[dict] = [{"role": "user", "content": context}]
    # Replay conversation as alternating user/assistant turns
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    # Append new user message
    messages.append({"role": "user", "content": user_message})

    # Merge consecutive same-role messages (context + first user msg if history is empty)
    merged: list[dict] = []
    for m in messages:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n\n" + m["content"]
        else:
            merged.append(m)

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=CHAT_SYSTEM,
        messages=merged,
    )

    text = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return text, tokens
