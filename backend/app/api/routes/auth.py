import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.session_store import session_store
from ...core.composio_client import (
    email_to_user_id,
    initiate_connection,
    check_all_connections,
)
from ...core.agent import preload_session, evict_tools_cache
from ...core.token_store import create_token, revoke_token
from ...core.history_store import clear_history
from ...core.profile_store import clear_profile
from ...config.settings import settings
from ...models.schemas import (
    AuthInitiateRequest,
    AuthInitiateResponse,
    AuthStatusResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/initiate", response_model=AuthInitiateResponse)
async def initiate_auth(request: AuthInitiateRequest):
    """
    Begin Google OAuth for a user identified by email.

    Returns {connected: true, session_token: "..."} if already connected via Composio.
    Otherwise returns {connected: false, auth_url: "<google-oauth-url>"}.
    """
    user_id = email_to_user_id(request.email)
    session = session_store.get_or_create(request.email)

    redirect_url = (
        request.callback_url
        or f"{settings.frontend_url}/auth/callback"
    )

    try:
        auth_url = await asyncio.to_thread(
            initiate_connection, user_id, redirect_url, request.agent_type
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Composio connection error: {exc}",
        )

    if auth_url is None:
        session.is_connected = True
        session_store.update(session)
        asyncio.create_task(preload_session(request.email))
        token = create_token(request.email)
        return AuthInitiateResponse(connected=True, session_token=token)

    return AuthInitiateResponse(connected=False, auth_url=auth_url)


@router.get("/status/{email}", response_model=AuthStatusResponse)
async def get_auth_status(email: str):
    """
    Check whether a user's Google accounts are connected via Composio.
    Poll this after OAuth redirect until connected=true.
    Returns per-toolkit status (gmail_connected, calendar_connected).
    A session_token is returned once connected=true — the frontend must store it
    and include it in all subsequent API calls.
    """
    user_id = email_to_user_id(email)

    statuses = await asyncio.to_thread(check_all_connections, user_id)
    gmail_connected = statuses["gmail"]
    calendar_connected = statuses["calendar"]
    connected = gmail_connected and calendar_connected

    session = session_store.get_or_create(email)
    session.is_connected = connected
    session_store.update(session)

    token = None
    if connected:
        asyncio.create_task(preload_session(email))
        token = create_token(email)

    return AuthStatusResponse(
        connected=connected,
        gmail_connected=gmail_connected,
        calendar_connected=calendar_connected,
        email=email,
        session_token=token,
    )


class LogoutRequest(BaseModel):
    email: str


@router.post("/logout")
async def logout(request: LogoutRequest):
    """
    Full logout: revoke token, clear chat history, clear profile cache,
    and evict the in-memory session so the next login starts completely fresh.
    """
    user_id = email_to_user_id(request.email)
    revoke_token(request.email)
    clear_history(request.email)          # TinyDB: all three agents
    clear_profile(request.email)          # TinyDB: profile cache
    session_store.remove(request.email)   # in-memory session evicted
    evict_tools_cache(user_id)            # in-memory tool schema cache cleared
    return {"ok": True}
