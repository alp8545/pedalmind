import logging
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.database import User

logger = logging.getLogger("security")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    logger.info("JWT auth on %s %s — token: %s...", request.method, request.url.path, token[:20] if token else "NONE")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        exp = payload.get("exp")
        logger.info("JWT valid — user_id=%s exp=%s", user_id, datetime.fromtimestamp(exp, tz=timezone.utc).isoformat() if exp else "?")
        if user_id is None:
            logger.warning("JWT payload missing 'sub' field")
            raise credentials_exc
    except JWTError as e:
        logger.warning("JWT decode failed on %s %s: %s", request.method, request.url.path, e)
        raise credentials_exc

    user = await db.get(User, user_id)
    if user is None:
        logger.warning("JWT user_id=%s not found in DB", user_id)
        raise credentials_exc
    return user
