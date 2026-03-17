import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

logger = logging.getLogger("pedalmind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup — don't crash if DB is unavailable
    try:
        from app.core.database import engine
        from app.models.database import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ready")
    except Exception as exc:
        logger.warning("Could not initialise database tables: %s", exc)
    yield


app = FastAPI(title="PedalMind API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "https://pedalmind-web.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import auth, profile, rides, chat, sync, garmin_oauth  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(rides.router, prefix="/api/rides", tags=["rides"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(garmin_oauth.router, prefix="/api/garmin", tags=["garmin"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
