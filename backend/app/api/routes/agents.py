"""
Agent management routes.

  GET  /api/agents/greeting/{email}   — return a personalised greeting
  POST /api/agents/email-summarizer   — trigger the email summarizer for a user
"""

import json
import random
import re
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.email_summarizer import schedule_summarizer
from ...core.composio_client import execute_tool, email_to_user_id
from ...core.session_store import session_store
from ...core.profile_store import save_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])

# ── Greeting helpers ──────────────────────────────────────────────────────────

# Five variants; {time} = "morning" / "afternoon" / "evening", {name} = first name
_GREETING_TEMPLATES = [
    "Good {time}, {name}! Ready to tackle your inbox and calendar today?",
    "Hey {name}! What's on your plate — emails, meetings, or something else?",
    "Welcome back, {name}. Your assistant is standing by. What do you need?",
    "Hi {name}! I'm here for Gmail and Google Calendar. Where would you like to start?",
    "Hello, {name}! Let's make today productive — need help with emails or your schedule?",
]


def _time_of_day() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    return "evening"


def _name_from_email(email: str) -> str:
    """
    Derive a best-guess first name from an email address.
    e.g. john.doe@gmail.com  → "John"
         j_smith@company.com → "J"
    """
    local = email.split("@")[0]
    name = re.sub(r"[._\-+0-9]+", " ", local).strip().title()
    return name.split()[0] if name else "there"


def _fetch_display_name(user_id: str) -> str | None:
    """
    Fetch the user's display name from the From header of their most recent
    sent email.  Returns None if the call fails or produces no parseable name.
    """
    try:
        raw = execute_tool(
            user_id=user_id,
            tool_name="GMAIL_FETCH_EMAILS",
            tool_input={
                "max_results": 1,
                "label_ids": ["SENT"],
                "include_spam_trash": False,
            },
        )
        data = json.loads(raw)
        messages: list[dict] = []
        if isinstance(data, list):
            messages = data
        elif isinstance(data, dict):
            messages = (
                data.get("messages")
                or data.get("emails")
                or data.get("data", {}).get("messages", [])
                or []
            )
        if not messages:
            return None

        from_field = str(
            messages[0].get("from")
            or messages[0].get("From")
            or messages[0].get("sender")
            or ""
        )
        # "Display Name <email@example.com>" or "Display Name" → "Display Name"
        m = re.match(r'^"?([^"<@][^"<]*?)"?\s*(?:<|$)', from_field)
        if m:
            candidate = m.group(1).strip()
            if candidate and "@" not in candidate:
                return candidate
    except Exception as exc:
        logger.warning("greeting: could not fetch display name: %s", exc)
    return None


def _build_greeting(name: str) -> str:
    template = random.choice(_GREETING_TEMPLATES)
    return template.format(time=_time_of_day(), name=name.split()[0])


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/greeting/{email}")
async def get_greeting(email: str) -> dict:
    """
    Return a personalised greeting for the user.

    The user's display name is resolved once from their most recent sent email
    and cached in the session for all subsequent calls (e.g. New Conversation).
    Always returns a freshly selected variant so consecutive calls differ.
    """
    session = session_store.get(email)
    if not session or not session.is_connected:
        raise HTTPException(status_code=400, detail="User is not connected")

    # Use cached name or fetch it once per session
    if session.display_name is None:
        user_id = email_to_user_id(email)
        session.display_name = _fetch_display_name(user_id)
        session_store.update(session)
        save_profile(email, session.display_name, session.user_profile)

    # Use real display name for greeting if available; fall back to email-derived
    # name only for the greeting text — never expose the email-derived fallback as
    # "name" so the frontend doesn't cache a corrupted value in localStorage.
    effective_name = session.display_name or _name_from_email(email)
    greeting = _build_greeting(effective_name)
    return {"greeting": greeting, "name": session.display_name}


class EmailSummarizerRequest(BaseModel):
    email: str


class EmailSummarizerResponse(BaseModel):
    status: str   # "queued" | "skipped" | "disabled"


@router.post("/email-summarizer", response_model=EmailSummarizerResponse)
async def trigger_email_summarizer(body: EmailSummarizerRequest) -> EmailSummarizerResponse:
    """
    Trigger the background email summarizer for the given user.

    Returns immediately with a status:
    - "queued"   — task started in background
    - "skipped"  — already ran today (per persistent DB)
    - "disabled" — feature flag is off
    """
    session = session_store.get(body.email)
    if not session or not session.is_connected:
        raise HTTPException(status_code=400, detail="User is not connected")

    status = schedule_summarizer(body.email)
    return EmailSummarizerResponse(status=status)


@router.post("/email-summarizer/reset")
async def reset_email_summarizer(body: EmailSummarizerRequest) -> dict:
    """
    Clear the processed-ID history for this user so the summarizer will
    treat all emails as new on the next login.  Useful during testing.
    """
    from ...core.email_summarizer import reset_processed_ids
    removed = reset_processed_ids(body.email)
    return {"reset": removed}
