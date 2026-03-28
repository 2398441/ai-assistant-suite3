"""
Trigger routes:

  GET  /api/triggers/available          — list all supported trigger types
  GET  /api/triggers/active/{email}     — list this user's active subscriptions
  POST /api/triggers/subscribe          — enable a trigger for a user
  POST /api/triggers/unsubscribe        — disable a trigger by subscription ID
  POST /api/triggers/webhook            — Composio calls this when a trigger fires
  GET  /api/triggers/stream/{email}     — SSE stream: frontend subscribes to receive events
"""

import json
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request, Query, status
from fastapi.responses import StreamingResponse

from ...constants import (
    GMAIL_PAYLOAD_WRAPPER,
    GMAIL_FIELDS,
    CALENDAR_FIELDS,
    CALENDAR_PAYLOAD_WRAPPER,
    ATTENDEE_RESPONSE_FIELDS,
    STARTING_SOON_FIELDS,
)
from ...core.composio_client import (
    email_to_user_id,
    GMAIL_TRIGGERS,
    CALENDAR_TRIGGERS,
    enable_trigger,
    disable_trigger,
    list_active_triggers,
)

# Combined lookup used by webhook decoder and subscribe validator
ALL_TRIGGERS = {**GMAIL_TRIGGERS, **CALENDAR_TRIGGERS}
from ...core.trigger_store import publish, sse_generator
from ...core.session_store import session_store
from ...core.notifier import send_whatsapp, format_trigger_message
from ...core.token_store import validate_token
from ...models.schemas import (
    TriggerSubscribeRequest,
    TriggerSubscribeResponse,
    TriggerUnsubscribeRequest,
    TriggerUnsubscribeResponse,
    TriggerInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/triggers", tags=["triggers"])


def _require_token(email: str, token: str | None) -> None:
    if not validate_token(email, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please sign in again.",
        )


# ── Available triggers ─────────────────────────────────────────────────────────

@router.get("/available", response_model=list[TriggerInfo])
async def get_available_triggers():
    """Return the full list of supported trigger types (Gmail + Calendar)."""
    return [
        TriggerInfo(
            trigger_name=slug,
            label=meta["label"],
            description=meta["description"],
            icon=meta["icon"],
            config=meta.get("config"),
        )
        for slug, meta in ALL_TRIGGERS.items()
    ]


# ── Active subscriptions for a user ───────────────────────────────────────────

@router.get("/active/{email}", response_model=list[TriggerInfo])
async def get_active_triggers(email: str):
    """Return all supported triggers annotated with their subscription status for this user."""
    user_id = email_to_user_id(email)
    active = list_active_triggers(user_id)
    active_map = {a["trigger_name"]: a["subscription_id"] for a in active}

    return [
        TriggerInfo(
            trigger_name=slug,
            label=meta["label"],
            description=meta["description"],
            icon=meta["icon"],
            subscription_id=active_map.get(slug),
            config=meta.get("config"),
        )
        for slug, meta in ALL_TRIGGERS.items()
    ]


# ── Subscribe ─────────────────────────────────────────────────────────────────

@router.post("/subscribe", response_model=TriggerSubscribeResponse)
async def subscribe_trigger(request: TriggerSubscribeRequest):
    """Enable a Composio trigger for the authenticated user."""
    _require_token(request.email, request.session_token)
    session = session_store.get(request.email)
    if not session or not session.is_connected:
        raise HTTPException(status_code=403, detail="Google account not connected")

    if request.trigger_name not in ALL_TRIGGERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown trigger '{request.trigger_name}'. "
                   f"Valid options: {list(ALL_TRIGGERS.keys())}",
        )

    user_id = email_to_user_id(request.email)
    result = enable_trigger(user_id, request.trigger_name, request.config)
    return TriggerSubscribeResponse(**result)


# ── Unsubscribe ────────────────────────────────────────────────────────────────

@router.post("/unsubscribe", response_model=TriggerUnsubscribeResponse)
async def unsubscribe_trigger(request: TriggerUnsubscribeRequest):
    """Disable a Composio trigger by its subscription ID."""
    _require_token(request.email, request.session_token)
    result = disable_trigger(request.trigger_subscription_id)
    return TriggerUnsubscribeResponse(**result)


# ── Webhook receiver ───────────────────────────────────────────────────────────

@router.post("/webhook")
async def trigger_webhook(request: Request):
    """
    Composio POSTs here when a calendar trigger fires.

    Expected payload shape (Composio v1):
    {
      "trigger_name": "GOOGLECALENDAR_EVENT_CREATED",
      "payload": { ...event data... },
      "metadata": {
        "client_unique_user_id": "<composio_user_id>",
        "id": "<trigger_instance_id>",
        "connection_id": "<connected_account_id>",
        "triggerName": "GOOGLECALENDAR_EVENT_CREATED"
      }
    }
    """
    try:
        body = await request.json()
    except Exception:
        # Composio may send an empty or malformed body on test pings — ignore
        return {"ok": True}

    trigger_name: str = body.get("trigger_name") or body.get("triggerName", "")
    payload: dict = body.get("payload", body.get("data", {}))
    metadata: dict = body.get("metadata", {})

    # Resolve the user's email from the Composio user_id stored in metadata
    composio_user_id: str = metadata.get("client_unique_user_id", "")
    email = _user_id_to_email(composio_user_id)

    if not email:
        logger.warning("Trigger webhook: could not resolve email for user_id=%s", composio_user_id)
        return {"ok": True}

    meta = ALL_TRIGGERS.get(trigger_name, {})
    event = {
        "type": "trigger",
        "trigger_name": trigger_name,
        "label": meta.get("label", trigger_name),
        "icon": meta.get("icon", "🔔"),
        "payload": _summarise_payload(trigger_name, payload),
    }

    publish(email, event)
    logger.info("Trigger %s delivered to %s", trigger_name, email)

    # WhatsApp auto-notification intentionally disabled.
    # WA is only sent when the user explicitly clicks "Send test" in the UI
    # or when an agent tool call is made at the user's direct request.

    return {"ok": True}


# ── SSE stream ─────────────────────────────────────────────────────────────────

@router.get("/stream/{email}")
async def trigger_stream(email: str, token: str = Query(default="")):
    """
    Long-lived SSE endpoint.  The frontend connects here once after login
    and receives trigger events in real time.  Pass ?token=<session_token>.

    Events:
      data: {"type": "trigger", "trigger_name": "...", "label": "...", "icon": "...", "payload": {...}}
    """
    _require_token(email, token or None)
    session = session_store.get(email)
    if not session or not session.is_connected:
        raise HTTPException(status_code=403, detail="Google account not connected")

    return StreamingResponse(
        sse_generator(email),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _user_id_to_email(composio_user_id: str) -> str:
    """
    Reverse the email→user_id sanitisation to find a matching session.
    We iterate over open sessions; this is fine for small user counts.
    """
    for email, session in session_store.all_sessions():
        if email_to_user_id(email) == composio_user_id:
            return email
    return ""


def _summarise_payload(trigger_name: str, payload: dict) -> dict:
    """Extract the most useful fields from the raw trigger payload."""
    if not payload:
        return {}

    # ── Gmail triggers ─────────────────────────────────────────────────────
    if trigger_name.startswith("GMAIL_"):
        summary = {}
        # Composio wraps Gmail message data under GMAIL_PAYLOAD_WRAPPER or flat
        msg = payload.get(GMAIL_PAYLOAD_WRAPPER, payload)
        for key in GMAIL_FIELDS:
            if key in msg:
                summary[key] = msg[key]
        return summary

    # ── Google Calendar triggers ───────────────────────────────────────────
    event_data = payload.get(CALENDAR_PAYLOAD_WRAPPER, payload)
    summary = {}
    for key in CALENDAR_FIELDS:
        if key in event_data:
            summary[key] = event_data[key]

    if trigger_name == "GOOGLECALENDAR_ATTENDEE_RESPONSE_CHANGED":
        for key in ATTENDEE_RESPONSE_FIELDS:
            if key in payload:
                summary[key] = payload[key]

    if trigger_name == "GOOGLECALENDAR_EVENT_STARTING_SOON":
        for key in STARTING_SOON_FIELDS:
            if key in payload:
                summary[key] = payload[key]

    return summary
