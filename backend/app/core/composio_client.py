"""
Composio integration — composio v1.0.0-rc2 / composio-anthropic

Key API:
  composio.tools.get(user_id, toolkits=[...])                        → list[ToolParam]
  composio.tools.execute(slug, arguments, user_id,
                         dangerously_skip_version_check=True)         → dict
  composio.connected_accounts.initiate(...)                           → ConnectionRequest
  composio.connected_accounts.list(user_ids=[...], ...)               → ConnectedAccountListResponse
"""

import logging
import re
import json
import asyncio
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional

logger = logging.getLogger(__name__)

from composio import Composio
from composio_anthropic import AnthropicProvider

from ..config.settings import settings

_composio = Composio(
    provider=AnthropicProvider(),
    api_key=settings.composio_api_key,
)


def email_to_user_id(email: str) -> str:
    """Sanitise an email address to a valid Composio user_id."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", email.lower())


_AGENT_TOOLKITS: dict[str, list[str]] = {
    "gmail": ["gmail", "googlecontacts"],
}

# Full explicit list of all Google Calendar tools available in Composio.
# We use the `tools=` parameter instead of `toolkits=["googlecalendar"]` because
# the toolkit default only returns 20 of the 40 available tools, omitting critical
# ones like GOOGLECALENDAR_EVENTS_LIST, GOOGLECALENDAR_FIND_EVENT,
# GOOGLECALENDAR_UPDATE_EVENT, GOOGLECALENDAR_LIST_CALENDARS, etc.
# Calendar: trimmed from 40 to 10 core user-facing tools.
# Removed: ACL_* (sharing admin), *_WATCH (push channels), CHANNELS_STOP,
#          SYNC_EVENTS, COLORS_GET, SETTINGS_LIST, BATCH_EVENTS,
#          DUPLICATE_CALENDAR, CALENDAR_LIST_DELETE/INSERT/PATCH/UPDATE,
#          CALENDARS_DELETE, CALENDARS_UPDATE, CLEAR_CALENDAR,
#          EVENTS_MOVE, PATCH_CALENDAR, LIST_ACL_RULES, UPDATE_ACL_RULE,
#          FREE_BUSY_QUERY (dup of FIND_FREE_SLOTS), QUICK_ADD (dup of CREATE_EVENT),
#          EVENTS_INSTANCES (recurring only, rare), GET_CALENDAR (metadata only),
#          REMOVE_ATTENDEE (covered by PATCH/UPDATE_EVENT)
_CALENDAR_ALL_TOOLS = [
    "GOOGLECALENDAR_CALENDAR_LIST_GET",
    "GOOGLECALENDAR_CREATE_EVENT",
    "GOOGLECALENDAR_DELETE_EVENT",
    "GOOGLECALENDAR_EVENTS_LIST",
    "GOOGLECALENDAR_FIND_EVENT",
    "GOOGLECALENDAR_FIND_FREE_SLOTS",
    "GOOGLECALENDAR_GET_CURRENT_DATE_TIME",
    "GOOGLECALENDAR_LIST_CALENDARS",
    "GOOGLECALENDAR_PATCH_EVENT",
    "GOOGLECALENDAR_UPDATE_EVENT",
]

# Gmail: explicit list for workspace agent (trimmed from 20 to 11).
# Removed: BATCH_DELETE/MODIFY (bulk ops), CREATE/DELETE/GET_FILTER,
#          DELETE_DRAFT, DELETE_LABEL, GET_ATTACHMENT, GET_AUTO_FORWARDING
_GMAIL_WORKSPACE_TOOLS = [
    "GMAIL_ADD_LABEL_TO_EMAIL",
    "GMAIL_CREATE_EMAIL_DRAFT",
    "GMAIL_CREATE_LABEL",
    "GMAIL_DELETE_MESSAGE",
    "GMAIL_DELETE_THREAD",
    "GMAIL_FETCH_EMAILS",
    "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
    "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
    "GMAIL_FORWARD_MESSAGE",
    "GMAIL_GET_CONTACTS",
    "GMAIL_GET_DRAFT",
]


def get_tools(user_id: str, agent_type: str = "gmail") -> list:
    """
    Return Anthropic-compatible ToolParam list for the given agent type.
    agent_type: "gmail" | "calendar" | "workspace"

    Google Contacts is handled as a native tool in agent.py — not via Composio.
    Calendar — uses the explicit full tool list because the default
               toolkits=["googlecalendar"] only returns 20 of 40 tools.
    """
    if agent_type == "calendar":
        calendar_tools = _composio.tools.get(user_id=user_id, tools=_CALENDAR_ALL_TOOLS)
        contact_tools = _composio.tools.get(user_id=user_id, toolkits=["googlecontacts"])
        return calendar_tools + contact_tools
    if agent_type == "workspace":
        gmail_tools = _composio.tools.get(user_id=user_id, tools=_GMAIL_WORKSPACE_TOOLS)
        calendar_tools = _composio.tools.get(user_id=user_id, tools=_CALENDAR_ALL_TOOLS)
        return gmail_tools + calendar_tools
    toolkits = _AGENT_TOOLKITS.get(agent_type, ["gmail", "googlecontacts"])
    return _composio.tools.get(user_id=user_id, toolkits=toolkits)


def check_connection_status(user_id: str, toolkit: str = "gmail") -> bool:
    """Return True if the user has an active connection for the given toolkit."""
    try:
        result = _composio.connected_accounts.list(
            user_ids=[user_id],
            toolkit_slugs=[toolkit],
            statuses=["ACTIVE"],
        )
        return bool(result.items)
    except Exception:
        return False


def check_all_connections(user_id: str) -> dict[str, bool]:
    """Return connection status for both Gmail and Google Calendar."""
    return {
        "gmail":    check_connection_status(user_id, "gmail"),
        "calendar": check_connection_status(user_id, "googlecalendar"),
    }


def _auth_config_for(agent_type: str) -> str:
    """Return the correct Composio auth config ID for the given agent type."""
    if agent_type == "calendar":
        return settings.calendar_auth_config_id
    return settings.gmail_auth_config_id


def initiate_connection(
    user_id: str,
    redirect_url: str,
    agent_type: str = "gmail",
) -> Optional[str]:
    """
    Initiate Google OAuth for the user via Composio.
    Uses the Gmail auth config for the gmail agent and the Calendar auth config
    for the calendar agent.
    Returns the OAuth URL, or None if this toolkit is already connected.
    """
    toolkit = "googlecalendar" if agent_type == "calendar" else "gmail"
    if check_connection_status(user_id, toolkit):
        return None

    request = _composio.connected_accounts.initiate(
        user_id=user_id,
        auth_config_id=_auth_config_for(agent_type),
        callback_url=redirect_url,
    )
    return request.redirect_url


# ── Trigger management ────────────────────────────────────────────────────────

# Human-readable metadata for each supported trigger slug
GMAIL_TRIGGERS: dict[str, dict] = {
    "GMAIL_NEW_EMAIL_EVENT": {
        "label": "New Email Received",
        "description": "Fires when a new message arrives in Gmail",
        "icon": "📨",
        "config": {},
    },
    "GMAIL_MESSAGE_SENT": {
        "label": "Email Sent",
        "description": "Fires when the authenticated user sends a Gmail message",
        "icon": "📤",
        "config": {},
    },
}

CALENDAR_TRIGGERS: dict[str, dict] = {
    "GOOGLECALENDAR_EVENT_CREATED": {
        "label": "Event Created",
        "description": "Fires when a new calendar event is created",
        "icon": "✅",
        "config": {},
    },
    "GOOGLECALENDAR_EVENT_UPDATED": {
        "label": "Event Updated",
        "description": "Fires when an existing calendar event is modified",
        "icon": "✏️",
        "config": {},
    },
    "GOOGLECALENDAR_EVENT_CANCELLED": {
        "label": "Event Cancelled / Deleted",
        "description": "Fires when a calendar event is cancelled or deleted",
        "icon": "❌",
        "config": {},
    },
    "GOOGLECALENDAR_ATTENDEE_RESPONSE_CHANGED": {
        "label": "Attendee Response Changed",
        "description": "Fires when any attendee's RSVP changes (accepted / declined / tentative)",
        "icon": "🔔",
        "config": {},
    },
    "GOOGLECALENDAR_EVENT_STARTING_SOON": {
        "label": "Event Starting Soon",
        "description": "Fires when an event is within N minutes of starting",
        "icon": "⏰",
        "config": {"minutes_before": settings.calendar_reminder_minutes},
    },
    "GOOGLECALENDAR_CALENDAR_EVENT_SYNC": {
        "label": "Calendar Event Sync",
        "description": "Full-sync polling trigger: returns complete event data including attendees and metadata",
        "icon": "🔄",
        "config": {},
    },
}


def get_connected_account_id(user_id: str) -> Optional[str]:
    """Return the first active Google connected-account ID for this user."""
    try:
        result = _composio.connected_accounts.list(
            user_ids=[user_id],
            toolkit_slugs=["googlecalendar"],
            statuses=["ACTIVE"],
        )
        if result.items:
            return result.items[0].id
    except Exception:
        pass
    return None


def enable_trigger(
    user_id: str,
    trigger_name: str,
    config: Optional[dict] = None,
) -> dict:
    """
    Enable a Composio trigger for the given user.
    Returns {"ok": True, "trigger_subscription_id": "..."} or {"ok": False, "error": "..."}.
    """
    account_id = get_connected_account_id(user_id)
    if not account_id:
        return {"ok": False, "error": "No active Google Calendar connection found for this user"}

    trigger_config = {**(CALENDAR_TRIGGERS.get(trigger_name, {}).get("config", {})), **(config or {})}
    try:
        result = _composio.triggers.enable(
            connected_account_id=account_id,
            trigger_id=trigger_name,
            config=trigger_config,
        )
        return {"ok": True, "trigger_subscription_id": getattr(result, "id", None)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def disable_trigger(trigger_subscription_id: str) -> dict:
    """
    Disable a trigger by its subscription ID.
    Returns {"ok": True} or {"ok": False, "error": "..."}.
    """
    try:
        _composio.triggers.disable(trigger_id=trigger_subscription_id)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def list_active_triggers(user_id: str) -> list[dict]:
    """
    Return all active trigger subscriptions for this user.
    Each entry: {"trigger_name": str, "subscription_id": str, "config": dict}
    """
    account_id = get_connected_account_id(user_id)
    if not account_id:
        return []
    try:
        result = _composio.triggers.list(connected_account_id=account_id)
        items = result if isinstance(result, list) else getattr(result, "items", [])
        return [
            {
                "trigger_name": getattr(t, "trigger_id", getattr(t, "trigger_name", "")),
                "subscription_id": getattr(t, "id", ""),
                "config": getattr(t, "config", {}),
            }
            for t in items
        ]
    except Exception:
        return []


def _fetch_gmail_profile(user_id: str) -> dict:
    """Fetch Gmail profile metadata."""
    result: dict = {}
    try:
        raw = execute_tool(user_id, "GMAIL_GET_PROFILE", {})
        data = json.loads(raw)
        if data.get("emailAddress"):
            result["gmail_email"] = data["emailAddress"]
        if data.get("messagesTotal") is not None:
            result["gmail_messages_total"] = data["messagesTotal"]
        if data.get("threadsTotal") is not None:
            result["gmail_threads_total"] = data["threadsTotal"]
    except Exception:
        pass
    return result


def _fetch_calendar_settings(user_id: str) -> dict:
    """Fetch Calendar preferences (timezone, locale, formats)."""
    result: dict = {}
    _WEEK_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday",
                  "Thursday", "Friday", "Saturday"]
    try:
        raw = execute_tool(user_id, "GOOGLECALENDAR_SETTINGS_LIST", {})
        data = json.loads(raw)
        for item in data.get("items", data.get("settings", [])):
            key = item.get("id", "")
            val = item.get("value", "")
            if key == "timezone":
                result["timezone"] = val
            elif key == "locale":
                result["locale"] = val
            elif key == "dateFieldOrder":
                result["date_format"] = val
            elif key == "format24HourTime":
                result["time_format"] = "24-hour" if val == "true" else "12-hour"
            elif key == "defaultEventLength":
                result["default_event_length_mins"] = val
            elif key == "weekStart":
                try:
                    result["week_starts_on"] = _WEEK_DAYS[int(val)]
                except (ValueError, IndexError):
                    result["week_starts_on"] = val
            elif key == "defaultReminders":
                result["default_reminders"] = val
    except Exception:
        pass
    return result


def _fetch_calendar_list(user_id: str) -> dict:
    """Fetch the user's calendar list."""
    result: dict = {}
    try:
        raw = execute_tool(user_id, "GOOGLECALENDAR_LIST_CALENDARS", {})
        data = json.loads(raw)
        calendars = []
        for cal in data.get("items", data.get("calendars", [])):
            entry = {
                "name": cal.get("summary", ""),
                "primary": cal.get("primary", False),
                "id": cal.get("id", ""),
                "access_role": cal.get("accessRole", ""),
            }
            if entry["name"] or entry["id"]:
                calendars.append(entry)
        if calendars:
            result["calendars"] = calendars
    except Exception:
        pass
    return result




def _fetch_frequent_contacts(user_id: str) -> dict:
    """
    Pre-load the user's contacts from Composio Google Contacts toolkit.
    Returns {"frequent_contacts": [{"name": str, "email": str}, ...]}
    """
    try:
        raw = execute_tool(user_id, "GOOGLECONTACTS_LIST_CONTACTS", {
            "limit": settings.top_contacts_limit,
        })
        data = json.loads(raw)
        contacts_raw = (
            data.get("contacts")
            or data.get("results")
            or data.get("items")
            or (data if isinstance(data, list) else [])
        )
        contacts = []
        for c in contacts_raw:
            name = (
                c.get("name") or c.get("displayName") or c.get("display_name") or ""
            )
            email = c.get("email") or c.get("emailAddress") or ""
            if not email:
                emails = c.get("emailAddresses") or []
                if isinstance(emails, list) and emails:
                    email = (emails[0].get("value") or emails[0].get("email") or "")
            if email:
                contacts.append({"name": name.strip(), "email": email.strip().lower()})
        if contacts:
            return {"frequent_contacts": contacts}
    except Exception:
        pass
    return {}


def get_user_profile(user_id: str) -> dict:
    """
    Fetch a rich user profile from Google Workspace sources in parallel.
    All 3 sources run concurrently with a 10 s total timeout — a slow or
    failed source never blocks the others. Callers treat every key as optional.

    Sources (run in parallel):
      - GMAIL_GET_PROFILE              → Gmail display name, email, message/thread counts
      - GOOGLECALENDAR_SETTINGS_LIST   → timezone, locale, date/time format, week start
      - GOOGLECALENDAR_LIST_CALENDARS  → user's calendar list
    Then (sequential, needs timezone from settings):
      - GOOGLECALENDAR_GET_CURRENT_DATE_TIME → current local date/time

    Note: Google Contacts are not pre-fetched here — agents use the
    native google_contacts tool to look up contacts on demand.
    """
    profile: dict = {}

    # ── Parallel fetch of independent sources ─────────────────────────────────
    with ThreadPoolExecutor(max_workers=settings.profile_fetch_workers) as pool:
        futures = {
            "gmail":     pool.submit(_fetch_gmail_profile, user_id),
            "settings":  pool.submit(_fetch_calendar_settings, user_id),
            "calendars": pool.submit(_fetch_calendar_list, user_id),
            "contacts":  pool.submit(_fetch_frequent_contacts, user_id),
        }
        for key, future in futures.items():
            try:
                profile.update(future.result(timeout=settings.profile_fetch_timeout))
            except Exception:
                pass

    # ── Current datetime (needs timezone resolved above) ──────────────────────
    tz = profile.get("timezone", "UTC")
    try:
        raw = execute_tool(
            user_id, "GOOGLECALENDAR_GET_CURRENT_DATE_TIME", {"timezone": tz}
        )
        data = json.loads(raw)
        dt = (
            data.get("current_datetime")
            or data.get("datetime")
            or f"{data.get('current_date', '')} {data.get('current_time', '')}".strip()
        )
        if dt:
            profile["current_datetime"] = dt
    except Exception:
        pass

    return profile


# Default arguments injected when the LLM omits optional fields with low API defaults.
# LLM-supplied values always take precedence (merge order: defaults first, then tool_input).
_TOOL_ARG_DEFAULTS: dict[str, dict] = {
    "GOOGLECALENDAR_EVENTS_LIST": {"maxResults": 2000},
}


def execute_tool(user_id: str, tool_name: str, tool_input: dict) -> str:
    """
    Execute a Composio tool and return the result as a JSON string.

    Uses dangerously_skip_version_check=True because composio v1.0.0-rc2
    requires an explicit toolkit version for manual execution; skipping
    the check uses whichever version was fetched via get_tools().
    """
    merged_input = {**_TOOL_ARG_DEFAULTS.get(tool_name, {}), **tool_input}
    try:
        result = _composio.tools.execute(
            slug=tool_name,
            arguments=merged_input,
            user_id=user_id,
            dangerously_skip_version_check=True,
        )
        # v1.0.0-rc2 returns a plain dict (not a response object)
        if isinstance(result, dict):
            if "error" in result and result["error"]:
                return json.dumps({"error": result["error"], "success": False})
            return json.dumps(result.get("data", result))
        # Fallback for object-style response
        if result.successful:
            return json.dumps(result.data)
        return json.dumps({"error": result.error or "Tool execution failed", "success": False})
    except Exception as exc:
        return json.dumps({"error": str(exc), "success": False})
