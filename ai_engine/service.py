import json
from ai_engine.prompts import RIDE_ANALYSIS_SYSTEM, RIDE_ANALYSIS_USER, CHAT_SYSTEM, CHAT_CONTEXT_TEMPLATE

async def analyze_ride(ride_data: dict, athlete_profile: dict, recent_rides: list[dict], model: str = "claude-haiku-4-5-20251001", api_key: str = "") -> dict:
    # TODO: connect to Anthropic API
    return {"version": "1.0", "ride_id": ride_data.get("ride_id", ""), "model_used": model, "generated_at": "2026-01-01T00:00:00Z", "summary_text": "Placeholder — AI not connected yet.", "sections": [], "scores": {"overall": 0}, "flags": [{"type": "info", "message": "AI not yet connected"}]}

async def chat_response(user_message: str, athlete_profile: dict, training_summary_30d: str, recent_rides_with_analysis: str, conversation_history: list[dict], model: str = "claude-sonnet-4-6", api_key: str = "") -> str:
    # TODO: connect to Anthropic API with streaming
    return "Chat not yet connected."
