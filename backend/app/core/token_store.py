"""Persistence layer for Garmin garth tokens.

Stores the latest garth token bundle in the DB so it survives container
restarts on Render free-tier (where /tmp is wiped). On boot, the bundle
is restored to /tmp before garth.resume() is called.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session as async_session_maker
from app.models.database import GarminTokenStore

logger = logging.getLogger("garmin_token_store")

_TOKEN_DIR = Path("/tmp/garth_tokens")


def _read_bundle_from_disk() -> dict | None:
    """Read the current /tmp token files into a JSON-serialisable bundle."""
    if not _TOKEN_DIR.exists():
        return None
    bundle: dict = {}
    for f in _TOKEN_DIR.iterdir():
        if not f.is_file() or not f.name.endswith(".json"):
            continue
        try:
            bundle[f.name] = json.loads(f.read_text())
        except Exception as e:
            logger.warning("Skipping unreadable token file %s: %s", f.name, e)
    return bundle or None


def _write_bundle_to_disk(bundle: dict) -> None:
    _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    for fname, content in bundle.items():
        (_TOKEN_DIR / fname).write_text(json.dumps(content))


async def load_tokens_from_db_to_disk() -> bool:
    """Load the latest bundle from DB and write it to /tmp. Returns True on success."""
    try:
        async with async_session_maker() as session:
            res = await session.execute(select(GarminTokenStore).where(GarminTokenStore.id == 1))
            row = res.scalar_one_or_none()
            if row is None or not row.bundle_json:
                logger.info("No persisted Garmin tokens in DB")
                return False
            _write_bundle_to_disk(row.bundle_json)
            logger.info("Restored Garmin tokens from DB (updated_at=%s)", row.updated_at)
            return True
    except Exception as e:
        logger.warning("load_tokens_from_db_to_disk failed: %s", e)
        return False


async def save_disk_tokens_to_db() -> bool:
    """Snapshot the current /tmp bundle to the DB. Returns True on success."""
    bundle = _read_bundle_from_disk()
    if not bundle:
        return False
    try:
        async with async_session_maker() as session:
            res = await session.execute(select(GarminTokenStore).where(GarminTokenStore.id == 1))
            row = res.scalar_one_or_none()
            if row is None:
                row = GarminTokenStore(id=1, bundle_json=bundle)
                session.add(row)
            else:
                row.bundle_json = bundle
            await session.commit()
        logger.info("Persisted Garmin tokens to DB (%d files)", len(bundle))
        return True
    except Exception as e:
        logger.warning("save_disk_tokens_to_db failed: %s", e)
        return False


def access_token_expires_at() -> int | None:
    """Read access-token expiry timestamp (epoch seconds) from /tmp, or None."""
    f = _TOKEN_DIR / "oauth2_token.json"
    if not f.exists():
        return None
    try:
        return int(json.loads(f.read_text()).get("expires_at") or 0) or None
    except Exception:
        return None


def refresh_token_expires_at() -> int | None:
    """Read refresh-token expiry timestamp (epoch seconds) from /tmp, or None."""
    f = _TOKEN_DIR / "oauth2_token.json"
    if not f.exists():
        return None
    try:
        return int(json.loads(f.read_text()).get("refresh_token_expires_at") or 0) or None
    except Exception:
        return None


def seconds_until_access_expires() -> int | None:
    exp = access_token_expires_at()
    return None if exp is None else max(0, exp - int(time.time()))


def days_until_refresh_expires() -> float | None:
    exp = refresh_token_expires_at()
    return None if exp is None else (exp - time.time()) / 86400.0
