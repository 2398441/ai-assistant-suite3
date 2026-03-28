"""
Twilio WhatsApp notification helper.

Usage:
    await send_whatsapp(to="+919XXXXXXXXX", message="Hello from AI Assistant")

Requires these settings in backend/.env:
    TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_WHATSAPP_FROM=whatsapp:+14155238886   # sandbox, or your registered number
"""

import re
import logging
import httpx
from ..config.settings import settings

logger = logging.getLogger(__name__)

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def normalise_e164(phone: str) -> str:
    """
    Normalise *phone* to E.164 format (+<country_code><number>).

    Strips whitespace, dashes, dots, and parentheses, then validates:
      - Must start with '+' followed by a non-zero digit
      - Total digits (excluding '+') must be 7–15

    Raises ValueError with a user-friendly message if the number cannot be
    normalised to a valid E.164 string.
    """
    cleaned = re.sub(r"[\s\-().]+", "", phone.strip())
    if not cleaned.startswith("+"):
        raise ValueError(
            f"Phone number '{phone}' is missing a country code. "
            "Use E.164 format, e.g. +919876543210."
        )
    if not _E164_RE.match(cleaned):
        raise ValueError(
            f"Phone number '{phone}' is not a valid E.164 number. "
            "Expected format: + followed by 7–15 digits, e.g. +919876543210."
        )
    return cleaned


_WA_MAX_CHARS = 1500   # Twilio hard limit is 1600; keep headroom for multi-part encoding


async def send_whatsapp(to: str, message: str) -> tuple[bool, str]:
    """
    Send a WhatsApp message via Twilio.

    Validates and normalises *to* to E.164 before sending.
    Truncates *message* to _WA_MAX_CHARS to stay within Twilio's 1600-char limit.

    Returns (True, "") on success, (False, error_message) on failure.
    """
    if len(message) > _WA_MAX_CHARS:
        message = message[:_WA_MAX_CHARS - 20] + "\n…_(message truncated)_"
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        msg = "WhatsApp send skipped — Twilio credentials not configured"
        logger.warning(msg)
        return False, msg

    try:
        to = normalise_e164(to)
    except ValueError as exc:
        logger.error("WhatsApp send aborted — invalid number: %s", exc)
        return False, str(exc)

    # Ensure the "whatsapp:" prefix is present
    to_wa = to if to.startswith("whatsapp:") else f"whatsapp:{to}"

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.twilio_account_sid}/Messages.json"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.http_request_timeout) as client:
            resp = await client.post(
                url,
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data={
                    "From": settings.twilio_whatsapp_from,
                    "To":   to_wa,
                    "Body": message,
                },
            )
            if not resp.is_success:
                # Parse Twilio's error body for a human-readable reason
                try:
                    body = resp.json()
                    twilio_msg = body.get("message", "")
                    twilio_code = body.get("code", "")
                    more_info = body.get("more_info", "")
                    detail = twilio_msg or str(resp.status_code)
                    if twilio_code:
                        detail = f"[Twilio {twilio_code}] {detail}"
                    if more_info:
                        detail += f" — {more_info}"
                except Exception:
                    detail = f"HTTP {resp.status_code}"
                msg = f"WhatsApp delivery failed to {to}: {detail}"
                logger.error(msg)
                return False, msg
            logger.info("WhatsApp sent to %s  sid=%s", to, resp.json().get("sid"))
            return True, ""
    except Exception as exc:
        msg = f"WhatsApp send failed to {to}: {exc}"
        logger.error(msg)
        return False, msg


def format_trigger_message(event: dict) -> str:
    """Convert a trigger event dict into a human-readable WhatsApp message."""
    icon    = event.get("icon", "🔔")
    label   = event.get("label", event.get("trigger_name", "Event"))
    payload = event.get("payload", {})

    lines = [f"{icon} *{label}*"]

    if payload:
        # Gmail
        if "subject" in payload:
            lines.append(f"Subject: {payload['subject']}")
        if "from" in payload:
            lines.append(f"From: {payload['from']}")
        if "snippet" in payload:
            lines.append(payload["snippet"][:settings.whatsapp_snippet_chars])

        # Calendar
        if "summary" in payload or "title" in payload:
            lines.append(f"Event: {payload.get('summary') or payload.get('title')}")
        if "start" in payload:
            start = payload["start"]
            dt = start.get("dateTime") or start.get("date", "") if isinstance(start, dict) else start
            lines.append(f"Start: {dt}")
        if "minutes_until_start" in payload or "minutesUntilStart" in payload:
            mins = payload.get("minutes_until_start") or payload.get("minutesUntilStart")
            lines.append(f"Starting in: {mins} minutes")

    return "\n".join(lines)
