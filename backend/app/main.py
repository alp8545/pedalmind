import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger("pedalmind")


async def _migrate_schema(conn):
    """Create tables and add any missing columns to existing tables."""
    from sqlalchemy import inspect, text
    from app.models.database import Base

    # Create any new tables
    await conn.run_sync(Base.metadata.create_all)

    # Add missing columns and fix column types
    def _add_missing_columns(sync_conn):
        inspector = inspect(sync_conn)
        for table_name, table in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing_cols = {c["name"]: c for c in inspector.get_columns(table_name)}
            for col in table.columns:
                if col.name not in existing_cols:
                    col_type = col.type.compile(sync_conn.engine.dialect)
                    sync_conn.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type}')
                    )
                    logger.info("Added column %s.%s", table_name, col.name)

        # Migrate activities.id from INTEGER to BIGINT for large Garmin IDs
        if inspector.has_table("activities"):
            cols = {c["name"]: c for c in inspector.get_columns("activities")}
            id_col = cols.get("id")
            if id_col and str(id_col["type"]) == "INTEGER":
                sync_conn.execute(text('ALTER TABLE "activities" ALTER COLUMN "id" TYPE BIGINT'))
                logger.info("Migrated activities.id from INTEGER to BIGINT")

    await conn.run_sync(_add_missing_columns)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    # Create tables and migrate schema on startup — bounded so Render boot stays fast
    try:
        from app.core.database import engine

        async with asyncio.timeout(20):
            async with engine.begin() as conn:
                await _migrate_schema(conn)
        logger.info("Database tables ready")
    except Exception as exc:
        logger.warning("Could not initialise database tables: %s", exc)

    # Proactive Garmin token refresh — fire-and-forget, never block boot.
    # Internally goes through token_store.attempt_refresh which respects the
    # persistent backoff state, so a cold-start during a Garmin cooldown is a no-op.
    async def _safe_token_refresh():
        try:
            from app.core.garth_client import proactive_token_refresh
            await proactive_token_refresh()
        except Exception as exc:
            logger.warning("Garmin token warmup skipped: %s", exc)

    asyncio.create_task(_safe_token_refresh())

    # NOTE: no periodic refresh loop. Render free sleeps the container after
    # 15 min idle, so a long-interval loop never fires reliably. Refresh is
    # purely on-demand: triggered by ensure_auth_async() at the first user
    # request that actually needs Garmin. The chokepoint serializes everything.

    yield


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="PedalMind API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions so they return JSON (with CORS headers via middleware)."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


from app.routers import auth, profile, rides, chat, sync, garmin_oauth, garmin_sync, workout, trends, ride_records  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(rides.router, prefix="/api/rides", tags=["rides"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(garmin_oauth.router, prefix="/api/garmin", tags=["garmin"])
app.include_router(garmin_sync.router, prefix="/api/garmin", tags=["garmin-sync"])
app.include_router(workout.router, prefix="/api/garmin/workout", tags=["workout"])
app.include_router(trends.router, prefix="/api", tags=["trends"])
app.include_router(ride_records.router, prefix="/api/rides", tags=["ride-records"])


@app.get("/api/health")
async def health_check():
    """Liveness only — used by Render's platform health check AND the 14-min keep-warm cron.

    MUST NOT touch Garmin. Hitting Garmin from here is what caused the 2026-05
    death loop: every cron tick fired a refresh attempt, which re-armed Garmin's
    account-level 429 timer, perpetuating the block. Token refresh is now
    exclusively on-demand from `ensure_auth_async()` inside `garmin_api_call`.
    """
    return {"status": "ok"}


@app.get("/api/health/ready")
async def readiness_check():
    """Readiness — pings the DB. For external monitoring, NOT for Render's platform health check."""
    from app.core.database import engine
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "up"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "degraded", "db": str(e)[:120]})
