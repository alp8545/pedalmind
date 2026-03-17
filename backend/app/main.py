import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

logger = logging.getLogger("pedalmind")


async def _migrate_schema(conn):
    """Create tables and add any missing columns to existing tables."""
    from sqlalchemy import inspect, text
    from app.models.database import Base

    # Create any new tables
    await conn.run_sync(Base.metadata.create_all)

    # Add missing columns to existing tables
    def _add_missing_columns(sync_conn):
        inspector = inspect(sync_conn)
        for table_name, table in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            for col in table.columns:
                if col.name not in existing:
                    col_type = col.type.compile(sync_conn.engine.dialect)
                    sync_conn.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type}')
                    )
                    logger.info("Added column %s.%s", table_name, col.name)

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
