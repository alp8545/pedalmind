import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.database import (
    Activity,
    AthleteProfile,
    ChatConversation,
    ChatMessage,
    Ride,
    RideAnalysis,
    User,
)

logger = logging.getLogger(__name__)

# Log API key status at import time
logger.info("ANTHROPIC_API_KEY: %s (%d chars)",
            "SET" if settings.ANTHROPIC_API_KEY else "NOT SET",
            len(settings.ANTHROPIC_API_KEY))
logger.info("AI_MODEL_CHAT: %s", settings.AI_MODEL_CHAT)
logger.info("AI_MODEL_ANALYSIS: %s", settings.AI_MODEL_ANALYSIS)

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
            "preferred_language": "it",
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
        "preferred_language": profile.preferred_language or "it",
    }


async def _build_training_summary(user_id: str, db: AsyncSession) -> str:
    """Build comprehensive training summary from ALL activities."""
    from sqlalchemy import func as sqlfunc

    # Total stats
    total_result = await db.execute(select(sqlfunc.count()).select_from(Activity))
    total_count = total_result.scalar_one()

    if total_count == 0:
        return "Nessuna attivita nel database."

    # Per-period breakdowns
    now = datetime.utcnow()
    periods = [
        ("7 giorni", now - timedelta(days=7)),
        ("30 giorni", now - timedelta(days=30)),
        ("90 giorni", now - timedelta(days=90)),
        ("Stagione 2026", datetime(2026, 1, 1)),
        ("Storico completo", datetime(2000, 1, 1)),
    ]

    lines = [f"Totale attivita nel database: {total_count}"]

    for label, cutoff in periods:
        result = await db.execute(
            select(Activity).where(Activity.start_time >= cutoff)
        )
        acts = result.scalars().all()
        if not acts:
            continue
        total_sec = sum(a.duration_secs or 0 for a in acts)
        total_km = sum((a.distance_m or 0) / 1000 for a in acts)
        tss_vals = [a.tss for a in acts if a.tss]
        np_vals = [a.normalized_power for a in acts if a.normalized_power]
        total_tss = sum(tss_vals)
        avg_np = round(sum(np_vals) / len(np_vals)) if np_vals else 0

        lines.append(
            f"{label}: {len(acts)} uscite, {total_sec / 3600:.0f}h, {total_km:.0f}km, "
            f"TSS {total_tss:.0f}, NP medio {avg_np}W"
        )

    return "\n".join(lines)


async def _build_recent_rides_with_analysis(user_id: str, db: AsyncSession) -> str:
    """Build recent rides summary — last 20 activities."""
    result = await db.execute(
        select(Activity)
        .order_by(Activity.start_time.desc())
        .limit(20)
    )
    activities = result.scalars().all()

    if not activities:
        return "Nessuna attivita."

    lines: list[str] = []
    for a in activities:
        date_str = a.start_time.strftime('%Y-%m-%d') if a.start_time else '?'
        dist = f"{(a.distance_m or 0) / 1000:.1f}km"
        dur_min = int((a.duration_secs or 0) // 60)
        parts = [f"- {date_str} {a.name}: {dist}, {dur_min}min"]
        if a.normalized_power:
            parts.append(f"NP {a.normalized_power}W")
        if a.tss:
            parts.append(f"TSS {a.tss:.0f}")
        if a.intensity_factor:
            parts.append(f"IF {a.intensity_factor:.2f}")
        if a.avg_hr:
            parts.append(f"FC {a.avg_hr}bpm")
        if a.decoupling is not None:
            quality = "buono" if abs(a.decoupling) < 5 else "alto"
            parts.append(f"Decoupling: {a.decoupling:.1f}% ({quality} <5%)")
        elif a.raw_data and isinstance(a.raw_data, dict):
            dec = a.raw_data.get("decoupling_pct")
            if dec is not None:
                parts.append(f"Dec {dec:.1f}%")
        if a.hr_recovery_60s is not None:
            parts.append(f"Recupero HR: -{a.hr_recovery_60s}bpm in 60s")
        elif a.hr_recovery_30s is not None:
            parts.append(f"Recupero HR: -{a.hr_recovery_30s}bpm in 30s")
        lines.append(", ".join(parts))

    return "\n".join(lines)


async def _get_latest_activity(db: AsyncSession) -> str:
    """Get the most recent Garmin activity for context."""
    result = await db.execute(
        select(Activity).order_by(Activity.start_time.desc()).limit(1)
    )
    act = result.scalar_one_or_none()
    if not act:
        return "Nessuna attivita Garmin."

    parts = [
        f"Nome: {act.name}",
        f"Data: {act.start_time.strftime('%Y-%m-%d %H:%M') if act.start_time else '?'}",
    ]
    if act.normalized_power:
        parts.append(f"NP: {act.normalized_power}W")
    if act.tss:
        parts.append(f"TSS: {round(act.tss)}")
    if act.intensity_factor:
        parts.append(f"IF: {act.intensity_factor:.2f}")
    if act.avg_hr:
        parts.append(f"FC media: {act.avg_hr}bpm")
    if act.distance_m:
        parts.append(f"Distanza: {act.distance_m / 1000:.1f}km")
    if act.duration_secs:
        h = int(act.duration_secs // 3600)
        m = int((act.duration_secs % 3600) // 60)
        parts.append(f"Durata: {h}h{m:02d}m")
    if act.analysis_text:
        parts.append(f"Analisi: {act.analysis_text[:300]}")

    return " | ".join(parts)


async def _build_training_load(db: AsyncSession) -> str:
    """Get CTL/ATL/TSB training load summary via TrendService (Coggan EWMA)."""
    try:
        from app.services.trends import get_trend_summary
        return await get_trend_summary(db)
    except Exception as e:
        logger.warning("TrendService failed, degrading gracefully: %s", e)
        return "Dati trend non disponibili al momento."


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

@router.get("/health")
async def chat_health():
    """Health check: verify chat service is operational."""
    return {"status": "ok"}


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
@limiter.limit("20/minute")
async def send_message(
    request: Request,
    conv_id: str,
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from ai_engine.service import chat_response

    logger.info("send_message: user=%s conv=%s msg='%s...'",
                current_user.id, conv_id, body.content[:50])

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
    user_msg = ChatMessage(conversation_id=conv_id, role="user", content=body.content)
    db.add(user_msg)
    await db.flush()
    await db.refresh(user_msg)

    # Build context
    logger.info("send_message: building context...")
    profile_dict = await _get_athlete_profile_dict(current_user, db)
    summary_30d = await _build_training_summary(current_user.id, db)
    rides_14d = await _build_recent_rides_with_analysis(current_user.id, db)
    latest_act = await _get_latest_activity(db)
    load = await _build_training_load(db)
    history = await _get_conversation_history(conv_id, db)
    history = [m for m in history if m["content"] != body.content or m["role"] != "user"]

    logger.info("send_message: context built. history=%d msgs, latest_act=%s, load=%s",
                len(history), latest_act[:60] if latest_act else "none", load[:60] if load else "none")

    try:
        response_text, tokens = await chat_response(
            user_message=body.content,
            athlete_profile=profile_dict,
            training_summary_30d=summary_30d,
            recent_rides_with_analysis=rides_14d,
            conversation_history=history,
            model=settings.AI_MODEL_CHAT,
            api_key=settings.ANTHROPIC_API_KEY,
            latest_activity=latest_act,
            training_load=load,
        )
        logger.info("send_message: AI response received, tokens=%s", tokens)
    except Exception as e:
        logger.exception("send_message: AI call failed for conversation %s: %s", conv_id, e)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI service temporarily unavailable")

    # Store assistant message
    assistant_msg = ChatMessage(
        conversation_id=conv_id,
        role="assistant",
        content=response_text,
        model_used=settings.AI_MODEL_CHAT,
        tokens_used=tokens,
    )
    db.add(assistant_msg)

    if conv.title == "New Chat":
        conv.title = body.content[:80]

    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return SendMessageResponse(
        user_message=MessageResponse(
            id=user_msg.id, role=user_msg.role, content=user_msg.content,
            model_used=user_msg.model_used, tokens_used=user_msg.tokens_used,
            created_at=user_msg.created_at,
        ),
        assistant_message=MessageResponse(
            id=assistant_msg.id, role=assistant_msg.role, content=assistant_msg.content,
            model_used=assistant_msg.model_used, tokens_used=assistant_msg.tokens_used,
            created_at=assistant_msg.created_at,
        ),
    )
