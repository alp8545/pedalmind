import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

def gen_uuid() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    garmin_oauth_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    garmin_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    garmin_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    profile: Mapped["AthleteProfile"] = relationship(back_populates="user", uselist=False)
    rides: Mapped[list["Ride"]] = relationship(back_populates="user")
    conversations: Mapped[list["ChatConversation"]] = relationship(back_populates="user")

class AthleteProfile(Base):
    __tablename__ = "athlete_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    ftp_watts: Mapped[int] = mapped_column(Integer, default=200)
    max_hr: Mapped[int] = mapped_column(Integer, default=190)
    resting_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float] = mapped_column(Float, default=70.0)
    target_ftp_watts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    weekly_hours_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_meter_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    goals_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped["User"] = relationship(back_populates="profile")

class Ride(Base):
    __tablename__ = "rides"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    garmin_activity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ride_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_sec: Mapped[int] = mapped_column(Integer)
    distance_km: Mapped[float] = mapped_column(Float)
    fit_file_s3_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ride_data_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped["User"] = relationship(back_populates="rides")
    analysis: Mapped["RideAnalysis | None"] = relationship(back_populates="ride", uselist=False)

class RideAnalysis(Base):
    __tablename__ = "ride_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    ride_id: Mapped[str] = mapped_column(ForeignKey("rides.id"), unique=True)
    model_used: Mapped[str] = mapped_column(String(50))
    analysis_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ride: Mapped["Ride"] = relationship(back_populates="analysis")

class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200), default="New Chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="conversation")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("chat_conversations.id"))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    conversation: Mapped["ChatConversation"] = relationship(back_populates="messages")
