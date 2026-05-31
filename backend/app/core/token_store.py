"""Persistence layer for Garmin garth tokens AND the refresh state machine.

Stores the latest garth token bundle in the DB so it survives container
restarts on Render free-tier (where /tmp is wiped). Also persists the
refresh backoff state (auth_failure_count, auth_failure_until, in-flight
mutex) — without this, every cold-start wipes the in-memory backoff and
triggers a fresh refresh attempt that resets Garmin's account-level 429
timer, perpetuating the block indefinitely.

`attempt_refresh()` is THE single chokepoint for every Garmin OAuth refresh.
Anyone else who calls garth.client.refresh_oauth2() directly will break the
invariant and risk re-arming Garmin's block timer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session as async_session_maker
from app.models.database import GarminTokenStore

logger = logging.getLogger("garmin_token_store")

_TOKEN_DIR = Path("/tmp/garth_tokens")

# Backoff ladder for repeated 429s on the OAuth exchange endpoint.
# Garmin's account-level block lasts 12–48h; each retry resets that timer,
# so we MUST wait long enough between attempts that the block can expire.
_BACKOFF_LADDER_SECONDS = [
    30 * 60,       # 30 min
    2 * 3600,      # 2 h
    6 * 3600,      # 6 h
    24 * 3600,     # 24 h
    24 * 3600,     # 24 h (cap)
]

# Don't refresh again within this window if a previous refresh just succeeded
# (de-duplicates across container restarts / concurrent kickers).
_MIN_INTERVAL_BETWEEN_REFRESHES_SECONDS = 5 * 60

# A refresh that hasn't completed in this many seconds is considered stuck —
# the in-flight mutex is treated as stale and the next caller may proceed.
_IN_FLIGHT_STALE_SECONDS = 5 * 60

# In-process serializer for attempt_refresh: prevents multiple async tasks in the
# SAME worker from racing past the DB gate. The persistent DB state (in-flight,
# backoff) plus SELECT...FOR UPDATE handles the cross-worker case; this lock is
# the cheap belt-and-braces for the common case (single Render free worker).
_REFRESH_INPROCESS_LOCK = asyncio.Lock()


def _backoff_for(failure_count: int) -> int:
    """Return backoff seconds for the Nth consecutive failure (1-indexed)."""
    idx = max(0, min(failure_count - 1, len(_BACKOFF_LADDER_SECONDS) - 1))
    return _BACKOFF_LADDER_SECONDS[idx]


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


# ---- Refresh state machine (persistent across container restarts) ----


async def get_refresh_state() -> dict:
    """Snapshot of the persistent refresh state. Safe to call without a row existing."""
    try:
        async with async_session_maker() as session:
            res = await session.execute(select(GarminTokenStore).where(GarminTokenStore.id == 1))
            row = res.scalar_one_or_none()
            if row is None:
                return {
                    "auth_failure_count": 0,
                    "auth_failure_until": None,
                    "last_refresh_attempt_at": None,
                    "last_refresh_success_at": None,
                    "refresh_in_flight": False,
                    "refresh_in_flight_since": None,
                    "last_429_at": None,
                    "last_error": None,
                }
            return {
                "auth_failure_count": row.auth_failure_count or 0,
                "auth_failure_until": row.auth_failure_until,
                "last_refresh_attempt_at": row.last_refresh_attempt_at,
                "last_refresh_success_at": row.last_refresh_success_at,
                "refresh_in_flight": bool(row.refresh_in_flight),
                "refresh_in_flight_since": row.refresh_in_flight_since,
                "last_429_at": row.last_429_at,
                "last_error": row.last_error,
            }
    except Exception as e:
        logger.warning("get_refresh_state failed: %s", e)
        return {
            "auth_failure_count": 0,
            "auth_failure_until": None,
            "last_refresh_attempt_at": None,
            "last_refresh_success_at": None,
            "refresh_in_flight": False,
            "refresh_in_flight_since": None,
            "last_429_at": None,
            "last_error": None,
        }


async def reset_backoff_state(reason: str = "manual reset") -> None:
    """Clear all backoff state. Used by /auth/reset and /auth/inject-tokens."""
    try:
        async with async_session_maker() as session:
            res = await session.execute(select(GarminTokenStore).where(GarminTokenStore.id == 1))
            row = res.scalar_one_or_none()
            if row is None:
                return
            row.auth_failure_count = 0
            row.auth_failure_until = None
            row.refresh_in_flight = False
            row.refresh_in_flight_since = None
            row.last_error = None
            await session.commit()
        logger.info("Backoff state reset: %s", reason)
    except Exception as e:
        logger.warning("reset_backoff_state failed: %s", e)


def auth_backoff_remaining_seconds(state: dict) -> int:
    """How many seconds until the backoff window closes. 0 if not in backoff."""
    until = state.get("auth_failure_until")
    if until is None:
        return 0
    delta = (until - datetime.utcnow()).total_seconds()
    return max(0, int(delta))


async def _claim_in_flight(force: bool) -> tuple[bool, dict]:
    """Try to acquire the cross-container in-flight lock. Returns (claimed, state).

    Uses a transactional SELECT-then-UPDATE on the singleton row. If `force=True`,
    bypasses backoff/in-flight/recently-refreshed gates.
    """
    now = datetime.utcnow()
    async with async_session_maker() as session:
        # SELECT ... FOR UPDATE serialises across workers/containers: only one
        # transaction at a time can hold the row, preventing the read-then-write
        # race that lets multiple refreshes both pass the in_flight=False gate
        # and fire concurrent refresh_oauth2() calls (the May 2026 8x-429 bug).
        res = await session.execute(
            select(GarminTokenStore)
            .where(GarminTokenStore.id == 1)
            .with_for_update()
        )
        row = res.scalar_one_or_none()

        if row is None:
            # No row yet — create one and claim immediately
            row = GarminTokenStore(id=1, bundle_json={})
            session.add(row)

        state = {
            "auth_failure_count": row.auth_failure_count or 0,
            "auth_failure_until": row.auth_failure_until,
            "last_refresh_attempt_at": row.last_refresh_attempt_at,
            "last_refresh_success_at": row.last_refresh_success_at,
            "refresh_in_flight": bool(row.refresh_in_flight),
            "refresh_in_flight_since": row.refresh_in_flight_since,
            "last_429_at": row.last_429_at,
            "last_error": row.last_error,
        }

        if not force:
            # Gate 1: another refresh is in flight and not yet stale
            if state["refresh_in_flight"] and state["refresh_in_flight_since"]:
                age = (now - state["refresh_in_flight_since"]).total_seconds()
                if age < _IN_FLIGHT_STALE_SECONDS:
                    return False, {**state, "skip_reason": "in_flight", "in_flight_age_seconds": int(age)}

            # Gate 2: backoff active
            if state["auth_failure_until"] and state["auth_failure_until"] > now:
                retry_after = int((state["auth_failure_until"] - now).total_seconds())
                return False, {**state, "skip_reason": "backoff", "retry_after_seconds": retry_after}

            # Gate 3: we just refreshed successfully
            if state["last_refresh_success_at"]:
                since = (now - state["last_refresh_success_at"]).total_seconds()
                if since < _MIN_INTERVAL_BETWEEN_REFRESHES_SECONDS:
                    return False, {**state, "skip_reason": "recently_refreshed", "since_seconds": int(since)}

        # Claim it
        row.refresh_in_flight = True
        row.refresh_in_flight_since = now
        row.last_refresh_attempt_at = now
        if force:
            row.auth_failure_count = 0
            row.auth_failure_until = None
        await session.commit()
        state["refresh_in_flight"] = True
        state["refresh_in_flight_since"] = now
        return True, state


async def _record_success() -> None:
    """Mark refresh as succeeded: clear backoff + in-flight, stamp success."""
    now = datetime.utcnow()
    async with async_session_maker() as session:
        res = await session.execute(select(GarminTokenStore).where(GarminTokenStore.id == 1))
        row = res.scalar_one_or_none()
        if row is None:
            return
        row.refresh_in_flight = False
        row.refresh_in_flight_since = None
        row.auth_failure_count = 0
        row.auth_failure_until = None
        row.last_refresh_success_at = now
        row.last_error = None
        await session.commit()


async def _record_failure(reason: str, is_rate_limit: bool, current_count: int) -> int:
    """Mark refresh as failed: increment count, set backoff, clear in-flight.

    Returns the new failure count.
    """
    now = datetime.utcnow()
    new_count = (current_count or 0) + 1
    backoff = _backoff_for(new_count)
    async with async_session_maker() as session:
        res = await session.execute(select(GarminTokenStore).where(GarminTokenStore.id == 1))
        row = res.scalar_one_or_none()
        if row is None:
            return new_count
        row.refresh_in_flight = False
        row.refresh_in_flight_since = None
        row.auth_failure_count = new_count
        row.auth_failure_until = now + timedelta(seconds=backoff)
        row.last_error = reason[:500]
        if is_rate_limit:
            row.last_429_at = now
        await session.commit()
    logger.warning(
        "Garmin refresh failure #%d — backoff %ds (%s). Reason: %s",
        new_count, backoff, "rate-limited" if is_rate_limit else "other", reason,
    )
    return new_count


async def attempt_refresh(force: bool = False) -> dict:
    """THE chokepoint for every Garmin OAuth refresh.

    Flow:
      1. Try to claim the persistent in-flight mutex (DB-backed, cross-container).
         If gated by backoff / in-flight / recently-refreshed → return early.
      2. Reload tokens from DB to /tmp (defeats garth's bug that wipes
         in-memory oauth1_token after any previous error).
      3. Call garth.client.refresh_oauth2() under the in-process asyncio lock.
      4. On success → save bundle to DB, reset backoff.
      5. On 429 → preserve tokens, engage long backoff (30min → 24h).
      6. On 401/403 → engage backoff, leave tokens for /auth/inject-tokens recovery.

    Returns a dict describing the outcome. Never raises.
    """
    # Local import to avoid circular dependency at module load time.
    from app.core.garth_client import (
        _garmin_lock,
        _is_rate_limit,
        _is_token_invalid,
    )
    import garth

    # In-process serializer: holds for the WHOLE refresh — claim, network call,
    # record outcome. Without this, concurrent async tasks in the same worker
    # could both pass _claim_in_flight (which now uses SELECT FOR UPDATE but
    # commits between tasks) and fire two refresh_oauth2() calls back-to-back,
    # both 429-ing and inflating auth_failure_count.
    async with _REFRESH_INPROCESS_LOCK:
        claimed, state = await _claim_in_flight(force=force)
        if not claimed:
            return {"refreshed": False, **state}

        # Reload fresh state from DB to disk — defeats garth's oauth1_token=None bug
        await load_tokens_from_db_to_disk()

        def _do_refresh() -> tuple[bool, str | None, Exception | None]:
            try:
                garth.resume(str(_TOKEN_DIR))
                garth.client.refresh_oauth2()
                return True, None, None
            except Exception as exc:
                return False, str(exc)[:500], exc

        try:
            async with _garmin_lock:
                ok, err_msg, exc = await asyncio.to_thread(_do_refresh)
        except Exception as exc:
            await _record_failure(f"unexpected: {exc}"[:500], is_rate_limit=False,
                                  current_count=state["auth_failure_count"])
            return {"refreshed": False, "error": str(exc)[:500]}

        if ok:
            try:
                await save_disk_tokens_to_db()
            except Exception as save_err:
                logger.warning("Refresh succeeded but DB persist failed: %s", save_err)
            await _record_success()
            return {
                "refreshed": True,
                "access_token_seconds_left": seconds_until_access_expires(),
                "refresh_token_days_left": days_until_refresh_expires(),
            }

        # Failure path
        is_rl = exc is not None and _is_rate_limit(exc)
        is_invalid = exc is not None and _is_token_invalid(exc)
        new_count = await _record_failure(
            reason=err_msg or "unknown error",
            is_rate_limit=is_rl,
            current_count=state["auth_failure_count"],
        )
        return {
            "refreshed": False,
            "error": err_msg,
            "rate_limited": is_rl,
            "token_invalid": is_invalid,
            "auth_failure_count": new_count,
            "auth_failure_until_in_seconds": _backoff_for(new_count),
        }
