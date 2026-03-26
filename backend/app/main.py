import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    # Create tables and migrate schema on startup
    try:
        from app.core.database import engine

        async with engine.begin() as conn:
            await _migrate_schema(conn)
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

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions so they return JSON (with CORS headers via middleware)."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}"},
    )


from app.routers import auth, profile, rides, chat, sync, garmin_oauth, garmin_sync  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(rides.router, prefix="/api/rides", tags=["rides"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(garmin_oauth.router, prefix="/api/garmin", tags=["garmin"])
app.include_router(garmin_sync.router, prefix="/api/garmin", tags=["garmin-sync"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
