import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

from .wa_store import load_wa_settings
from .profile_store import load_profile
from .history_store import load_history


@dataclass
class Session:
    email: str                          # primary key — stable across restarts
    is_connected: bool = False
    # Per-agent conversation histories
    gmail_messages:     list[dict[str, Any]] = field(default_factory=list)
    calendar_messages:  list[dict[str, Any]] = field(default_factory=list)
    workspace_messages: list[dict[str, Any]] = field(default_factory=list)
    outlook_messages:   list[dict[str, Any]] = field(default_factory=list)
    # Cached system prompts — built once on the first call per subagent
    gmail_system_prompt:     Optional[str] = None
    calendar_system_prompt:  Optional[str] = None
    workspace_system_prompt: Optional[str] = None
    outlook_system_prompt:   Optional[str] = None
    # Display name fetched once from the SENT folder From header
    display_name: Optional[str] = None
    # User profile fetched once on auth (timezone, locale, calendars, etc.)
    user_profile: dict[str, Any] = field(default_factory=dict)
    # When the profile was last fetched — None means never fetched
    profile_fetched_at: Optional[datetime] = None
    # WhatsApp notification settings (E.164 number + opt-in flag)
    whatsapp_number: str = ""
    wa_notifications_enabled: bool = False

    def get_system_prompt(self, agent_type: str) -> Optional[str]:
        if agent_type == "gmail":
            return self.gmail_system_prompt
        if agent_type == "workspace":
            return self.workspace_system_prompt
        if agent_type == "outlook":
            return self.outlook_system_prompt
        return self.calendar_system_prompt

    def set_system_prompt(self, agent_type: str, prompt: str) -> None:
        if agent_type == "gmail":
            self.gmail_system_prompt = prompt
        elif agent_type == "workspace":
            self.workspace_system_prompt = prompt
        elif agent_type == "outlook":
            self.outlook_system_prompt = prompt
        else:
            self.calendar_system_prompt = prompt

    def get_messages(self, agent_type: str) -> list[dict[str, Any]]:
        if agent_type == "gmail":
            return self.gmail_messages
        if agent_type == "workspace":
            return self.workspace_messages
        if agent_type == "outlook":
            return self.outlook_messages
        return self.calendar_messages

    def set_messages(self, agent_type: str, messages: list[dict[str, Any]]) -> None:
        if agent_type == "gmail":
            self.gmail_messages = messages
        elif agent_type == "workspace":
            self.workspace_messages = messages
        elif agent_type == "outlook":
            self.outlook_messages = messages
        else:
            self.calendar_messages = messages

    def clear_messages(self, agent_type: Optional[str] = None) -> None:
        """Clear conversation history for the specified agent, or all."""
        if agent_type is None or agent_type == "gmail":
            self.gmail_messages = []
        if agent_type is None or agent_type == "calendar":
            self.calendar_messages = []
        if agent_type is None or agent_type == "workspace":
            self.workspace_messages = []
        if agent_type is None or agent_type == "outlook":
            self.outlook_messages = []


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get_or_create(self, email: str) -> Session:
        with self._lock:
            if email not in self._sessions:
                wa_number, wa_enabled = load_wa_settings(email)
                display_name, profile, fetched_at, _provider = load_profile(email)
                session = Session(
                    email=email,
                    whatsapp_number=wa_number,
                    wa_notifications_enabled=wa_enabled,
                    display_name=display_name,
                    user_profile=profile,
                    profile_fetched_at=fetched_at,
                )
                # Restore persisted conversation history (survives backend restarts)
                for agent_type in ("gmail", "calendar", "workspace", "outlook"):
                    msgs = load_history(email, agent_type)
                    if msgs:
                        session.set_messages(agent_type, msgs)
                self._sessions[email] = session
            return self._sessions[email]

    def get(self, email: str) -> Optional[Session]:
        return self._sessions.get(email)

    def update(self, session: Session) -> None:
        with self._lock:
            self._sessions[session.email] = session

    def clear_messages(self, email: str, agent_type: Optional[str] = None) -> None:
        with self._lock:
            session = self._sessions.get(email)
            if session:
                session.clear_messages(agent_type)

    def remove(self, email: str) -> None:
        """Evict the in-memory session for a user (called on logout)."""
        with self._lock:
            self._sessions.pop(email, None)

    def all_sessions(self):
        """Return (email, session) pairs for all active sessions."""
        with self._lock:
            return list(self._sessions.items())


session_store = SessionStore()
