import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.database import (
    AthleteProfile,
    ChatConversation,
    ChatMessage,
    Ride,
    RideAnalysis,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreateRequest(BaseModel):
    title: str = "New Chat"


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    model_used: str | None = None
    tokens_used: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str


class SendMessageResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

async def _get_athlete_profile_dict(user: User, db: AsyncSession) -> dict:
    result = await db.execute(
        select(AthleteProfile).where(AthleteProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        return {
            "athlete_id": user.id, "name": user.name,
            "ftp_watts": 265, "max_hr": 192, "resting_hr": 57, "weight_kg": 68.0,
            "preferred_language": "en",
        }
    return {
        "athlete_id": user.id,
        "name": user.name,
        "ftp_watts": profile.ftp_watts,
        "max_hr": profile.max_hr,
        "resting_hr": profile.resting_hr,
        "weight_kg": profile.weight_kg,
        "power_meter_type": profile.power_meter_type,
        "goals_text": profile.goals_text,
        "preferred_language": profile.preferred_language,
    }


async def _build_training_summary_30d(user_id: str, db: AsyncSession) -> str:
    cutoff = datetime.utcnow() - timedelta(days=30)
    result = await db.execute(
        select(Ride)
        .where(Ride.user_id == user_id, Ride.ride_date >= cutoff)
        .order_by(Ride.ride_date.desc())
    )
    rides = result.scalars().all()

    if not rides:
        return "No rides in the last 30 days."

    total_rides = len(rides)
    total_sec = sum(r.duration_sec for r in rides)
    total_km = sum(r.distance_km for r in rides)

    tss_values: list[float] = []
    np_values: list[int] = []
    for r in rides:
        summary = r.ride_data_json.get("summary", {})
        tss = summary.get("training_stress_score")
        np_w = summary.get("normalized_power_w")
        if tss is not None:
            tss_values.append(tss)
        if np_w is not None:
            np_values.append(np_w)

    total_tss = sum(tss_values) if tss_values else 0
    avg_np = round(sum(np_values) / len(np_values)) if np_values else 0

    return (
        f"Last 30 days: {total_rides} rides, "
        f"{total_sec / 3600:.1f} hours, "
        f"{total_km:.0f} km, "
        f"total TSS {total_tss:.0f}, "
        f"avg NP {avg_np}W"
    )


async def _build_recent_rides_with_analysis(user_id: str, db: AsyncSession) -> str:
    cutoff = datetime.utcnow() - timedelta(days=14)
    result = await db.execute(
        select(Ride)
        .options(selectinload(Ride.analysis))
        .where(Ride.user_id == user_id, Ride.ride_date >= cutoff)
        .order_by(Ride.ride_date.desc())
        .limit(10)
    )
    rides = result.scalars().all()

    if not rides:
        return "No rides in the last 14 days."

    lines: list[str] = []
    for r in rides:
        summary = r.ride_data_json.get("summary", {})
        line = (
            f"- {r.ride_date.strftime('%Y-%m-%d')}: "
            f"{summary.get('distance_km', 0):.1f} km, "
            f"{r.duration_sec // 60} min, "
            f"NP {summary.get('normalized_power_w', '?')}W, "
            f"TSS {summary.get('training_stress_score', '?')}"
        )
        if r.analysis:
            a = r.analysis.analysis_json
            ride_type = a.get("ride_type_detected", "")
            summary_text = a.get("summary_text", "")
            line += f" | {ride_type}: {summary_text}"
        lines.append(line)

    return "\n".join(lines)


async def _get_conversation_history(conv_id: str, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return [
        {"role": m.role, "content": m.content}
        for m in result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = ChatConversation(user_id=current_user.id, title=body.title)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatConversation)
        .where(ChatConversation.user_id == current_user.id)
        .order_by(ChatConversation.created_at.desc())
    )
    return result.scalars().all()


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify ownership
    conv_result = await db.execute(
        select(ChatConversation.id).where(
            ChatConversation.id == conv_id,
            ChatConversation.user_id == current_user.id,
        )
    )
    if conv_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return result.scalars().all()


@router.post("/conversations/{conv_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conv_id: str,
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from ai_engine.service import chat_response

    # Verify ownership
    conv_result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_id,
            ChatConversation.user_id == current_user.id,
        )
    )
    conv = conv_result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Store user message
    user_msg = ChatMessage(
        conversation_id=conv_id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    await db.flush()
    await db.refresh(user_msg)

    # Build context
    profile_dict = await _get_athlete_profile_dict(current_user, db)
    summary_30d = await _build_training_summary_30d(current_user.id, db)
    rides_14d = await _build_recent_rides_with_analysis(current_user.id, db)
    history = await _get_conversation_history(conv_id, db)
    # Remove the message we just added (it's passed separately)
    history = [m for m in history if m["content"] != body.content or m["role"] != "user"]

    try:
        response_text, tokens = await chat_response(
            user_message=body.content,
            athlete_profile=profile_dict,
            training_summary_30d=summary_30d,
            recent_rides_with_analysis=rides_14d,
            conversation_history=history,
            model=settings.AI_MODEL_CHAT,
            api_key=settings.ANTHROPIC_API_KEY,
        )
    except Exception:
        logger.exception("Chat AI call failed for conversation %s", conv_id)
        await db.commit()  # keep user message saved
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI service unavailable")

    # Store assistant message
    assistant_msg = ChatMessage(
        conversation_id=conv_id,
        role="assistant",
        content=response_text,
        model_used=settings.AI_MODEL_CHAT,
        tokens_used=tokens,
    )
    db.add(assistant_msg)

    # Auto-title on first message
    if conv.title == "New Chat":
        conv.title = body.content[:80]

    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return SendMessageResponse(
        user_message=MessageResponse(
            id=user_msg.id,
            role=user_msg.role,
            content=user_msg.content,
            model_used=user_msg.model_used,
            tokens_used=user_msg.tokens_used,
            created_at=user_msg.created_at,
        ),
        assistant_message=MessageResponse(
            id=assistant_msg.id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            model_used=assistant_msg.model_used,
            tokens_used=assistant_msg.tokens_used,
            created_at=assistant_msg.created_at,
        ),
    )
