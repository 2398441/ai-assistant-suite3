"""
WhatsApp notification settings routes:

  GET  /api/notifications/whatsapp/{email}   — fetch current settings
  POST /api/notifications/whatsapp           — save phone number + enable/disable
  POST /api/notifications/whatsapp/test      — send a test message
"""

import logging
from fastapi import APIRouter, HTTPException, status

from ...core.session_store import session_store
from ...core.notifier import send_whatsapp
from ...core.wa_store import save_wa_settings
from ...core.token_store import validate_token
from ...config.settings import settings
from ...constants import WHATSAPP_TEST_MESSAGE, WHATSAPP_TEST_SEND_FAILED
from ...models.schemas import WhatsAppSettingsRequest, WhatsAppSettingsResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/whatsapp/{email}", response_model=WhatsAppSettingsResponse)
async def get_whatsapp_settings(email: str):
    session = session_store.get(email)
    if not session:
        return WhatsAppSettingsResponse(ok=True, whatsapp_number="", enabled=False,
                                        sandbox_keyword=settings.twilio_sandbox_keyword)
    return WhatsAppSettingsResponse(
        ok=True,
        whatsapp_number=session.whatsapp_number,
        enabled=session.wa_notifications_enabled,
        sandbox_keyword=settings.twilio_sandbox_keyword,
    )


def _require_token(email: str, token: str | None) -> None:
    if not validate_token(email, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please sign in again.",
        )


@router.post("/whatsapp", response_model=WhatsAppSettingsResponse)
async def save_whatsapp_settings(request: WhatsAppSettingsRequest):
    _require_token(request.email, request.session_token)
    session = session_store.get_or_create(request.email)
    session.whatsapp_number = request.whatsapp_number
    session.wa_notifications_enabled = request.enabled
    session_store.update(session)
    save_wa_settings(request.email, request.whatsapp_number, request.enabled)
    return WhatsAppSettingsResponse(
        ok=True,
        whatsapp_number=session.whatsapp_number,
        enabled=session.wa_notifications_enabled,
    )


@router.post("/whatsapp/test", response_model=WhatsAppSettingsResponse)
async def test_whatsapp(request: WhatsAppSettingsRequest):
    _require_token(request.email, request.session_token)
    if not request.whatsapp_number:
        raise HTTPException(status_code=400, detail="whatsapp_number is required")

    ok, err = await send_whatsapp(
        to=request.whatsapp_number,
        message=WHATSAPP_TEST_MESSAGE,
    )
    if not ok:
        return WhatsAppSettingsResponse(
            ok=False,
            whatsapp_number=request.whatsapp_number,
            enabled=request.enabled,
            error=err or WHATSAPP_TEST_SEND_FAILED,
        )
    return WhatsAppSettingsResponse(
        ok=True,
        whatsapp_number=request.whatsapp_number,
        enabled=request.enabled,
    )
