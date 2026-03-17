"""Garmin Connect OAuth 1.0a flow.

Endpoints to connect/disconnect a user's Garmin account.
Tokens are encrypted at rest with Fernet.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from requests_oauthlib import OAuth1Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.encryption import encrypt_token, decrypt_token
from app.core.security import get_current_user
from app.models.database import User

logger = logging.getLogger(__name__)

router = APIRouter()

GARMIN_REQUEST_TOKEN_URL = "https://connectapi.garmin.com/oauth-service/oauth/request_token"
GARMIN_AUTHORIZATION_URL = "https://connect.garmin.com/oauthConfirm"
GARMIN_ACCESS_TOKEN_URL = "https://connectapi.garmin.com/oauth-service/oauth/access_token"


def _check_garmin_configured():
    if not settings.GARMIN_CONSUMER_KEY or not settings.GARMIN_CONSUMER_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Garmin OAuth is not configured on this server",
        )


@router.get("/connect")
async def garmin_connect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start the Garmin OAuth 1.0a flow. Returns the authorization URL."""
    _check_garmin_configured()

    callback_url = f"{settings.APP_BASE_URL}/api/garmin/callback"

    oauth = OAuth1Session(
        settings.GARMIN_CONSUMER_KEY,
        client_secret=settings.GARMIN_CONSUMER_SECRET,
        callback_uri=callback_url,
    )

    try:
        fetch_response = oauth.fetch_request_token(GARMIN_REQUEST_TOKEN_URL)
    except Exception as e:
        logger.exception("Failed to fetch Garmin request token")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to Garmin: {e}",
        )

    # Store request token temporarily so we can verify in the callback
    current_user.garmin_request_token = fetch_response["oauth_token"]
    current_user.garmin_request_token_secret = fetch_response["oauth_token_secret"]
    await db.commit()

    authorization_url = oauth.authorization_url(GARMIN_AUTHORIZATION_URL)

    return {"authorization_url": authorization_url}


@router.get("/callback")
async def garmin_callback(
    oauth_token: str = Query(...),
    oauth_verifier: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Garmin redirects here after user authorizes. Exchanges for access token."""
    _check_garmin_configured()

    # Find the user who initiated this flow by request token
    from sqlalchemy import select

    result = await db.execute(
        select(User).where(User.garmin_request_token == oauth_token)
    )
    user = result.scalar_one_or_none()

    if user is None:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/settings?garmin=error&reason=unknown_token"
        )

    oauth = OAuth1Session(
        settings.GARMIN_CONSUMER_KEY,
        client_secret=settings.GARMIN_CONSUMER_SECRET,
        resource_owner_key=oauth_token,
        resource_owner_secret=user.garmin_request_token_secret,
        verifier=oauth_verifier,
    )

    try:
        access_response = oauth.fetch_access_token(GARMIN_ACCESS_TOKEN_URL)
    except Exception:
        logger.exception("Failed to exchange Garmin access token")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/settings?garmin=error&reason=token_exchange_failed"
        )

    # Store encrypted access tokens
    user.garmin_access_token_enc = encrypt_token(access_response["oauth_token"])
    user.garmin_access_token_secret_enc = encrypt_token(access_response["oauth_token_secret"])
    # Clear temporary request tokens
    user.garmin_request_token = None
    user.garmin_request_token_secret = None
    await db.commit()

    return RedirectResponse(url=f"{settings.FRONTEND_URL}/settings?garmin=success")


@router.get("/status")
async def garmin_status(current_user: User = Depends(get_current_user)):
    """Check if the current user has connected their Garmin account."""
    connected = (
        current_user.garmin_access_token_enc is not None
        and current_user.garmin_access_token_secret_enc is not None
    )
    return {"connected": connected}


@router.post("/disconnect")
async def garmin_disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove stored Garmin OAuth tokens."""
    current_user.garmin_access_token_enc = None
    current_user.garmin_access_token_secret_enc = None
    current_user.garmin_request_token = None
    current_user.garmin_request_token_secret = None
    current_user.garmin_user_id = None
    await db.commit()
    return {"status": "disconnected"}
