from pydantic import BaseModel
from typing import Optional


class AuthInitiateRequest(BaseModel):
    email: str
    callback_url: Optional[str] = None
    agent_type: str = "gmail"  # "gmail" | "calendar" — selects the auth config


class AuthInitiateResponse(BaseModel):
    connected: bool
    auth_url: Optional[str] = None
    session_token: Optional[str] = None   # present when connected=True


class AuthStatusResponse(BaseModel):
    connected: bool           # True only when BOTH gmail + calendar are connected
    gmail_connected: bool = False
    calendar_connected: bool = False
    email: Optional[str] = None
    session_token: Optional[str] = None   # present when connected=True


AgentType = str  # "gmail" | "calendar" | "workspace"


class ChatMessageRequest(BaseModel):
    email: str
    message: str
    agent_type: AgentType = "core"
    session_token: Optional[str] = None


class ClearMessagesRequest(BaseModel):
    email: str
    agent_type: Optional[AgentType] = None  # None → clear both
    session_token: Optional[str] = None


class ClearMessagesResponse(BaseModel):
    ok: bool


# ── Triggers ──────────────────────────────────────────────────────────────────

class TriggerSubscribeRequest(BaseModel):
    email: str
    trigger_name: str
    config: Optional[dict] = None  # e.g. {"minutes_before": 10} for EVENT_STARTING_SOON
    session_token: Optional[str] = None


class TriggerSubscribeResponse(BaseModel):
    ok: bool
    trigger_subscription_id: Optional[str] = None
    error: Optional[str] = None


class TriggerUnsubscribeRequest(BaseModel):
    trigger_subscription_id: str
    email: str                       # needed for token validation
    session_token: Optional[str] = None


class TriggerUnsubscribeResponse(BaseModel):
    ok: bool
    error: Optional[str] = None


class TriggerInfo(BaseModel):
    trigger_name: str
    label: str
    description: str
    icon: str
    subscription_id: Optional[str] = None  # set if already subscribed
    config: Optional[dict] = None


# ── WhatsApp notification settings ────────────────────────────────────────────

class WhatsAppSettingsRequest(BaseModel):
    email: str
    whatsapp_number: str        # E.164 e.g. "+919XXXXXXXXX"
    enabled: bool = True
    session_token: Optional[str] = None


class WhatsAppSettingsResponse(BaseModel):
    ok: bool
    whatsapp_number: str = ""
    enabled: bool = False
    sandbox_keyword: str = ""
    error: Optional[str] = None
