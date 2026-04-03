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


# Outlook: curated from 200+ tools to 31 core tools.
# Covers: email (list/get/search/compose/send/reply/forward/delete/move/batch),
#          folders, contacts (CRUD), calendar (create/view/update/delete/cancel/
#          find-meeting-times/free-busy/decline), profile, and mailbox settings.
_OUTLOOK_TOOLS = [
    # ── Email ──────────────────────────────────────────────────────────
    "OUTLOOK_LIST_MESSAGES",
    "OUTLOOK_GET_MESSAGE",
    "OUTLOOK_SEARCH_MESSAGES",
    "OUTLOOK_CREATE_DRAFT",
    "OUTLOOK_SEND_EMAIL",
    "OUTLOOK_SEND_DRAFT",
    "OUTLOOK_CREATE_DRAFT_REPLY",
    "OUTLOOK_CREATE_FORWARD_DRAFT",
    "OUTLOOK_FORWARD_MESSAGE",
    "OUTLOOK_DELETE_MESSAGE",
    "OUTLOOK_MOVE_MESSAGE",
    "OUTLOOK_BATCH_UPDATE_MESSAGES",
    # ── Folders ────────────────────────────────────────────────────────
    "OUTLOOK_CREATE_MAIL_FOLDER",
    "OUTLOOK_LIST_MAIL_FOLDERS",
    "OUTLOOK_GET_DRAFTS_MAIL_FOLDER",
    # ── Calendar / Meetings ────────────────────────────────────────────
    "OUTLOOK_CALENDAR_CREATE_EVENT",
    "OUTLOOK_GET_CALENDAR_VIEW",
    "OUTLOOK_LIST_EVENTS",
    "OUTLOOK_GET_EVENT",
    "OUTLOOK_UPDATE_CALENDAR_EVENT",
    "OUTLOOK_DELETE_CALENDAR_EVENT",
    "OUTLOOK_CANCEL_EVENT",
    "OUTLOOK_FIND_MEETING_TIMES",
    "OUTLOOK_GET_SCHEDULE",
    "OUTLOOK_DECLINE_EVENT",
    "OUTLOOK_LIST_CALENDARS",
    # ── Contacts ───────────────────────────────────────────────────────
    "OUTLOOK_CREATE_CONTACT",
    "OUTLOOK_LIST_USER_CONTACTS",
    "OUTLOOK_UPDATE_CONTACT",
    # ── Profile & Settings ─────────────────────────────────────────────
    "OUTLOOK_GET_PROFILE",
    "OUTLOOK_GET_MAILBOX_SETTINGS",
]


def get_tools(user_id: str, agent_type: str = "gmail") -> list:
    """
    Return Anthropic-compatible ToolParam list for the given agent type.
    agent_type: "gmail" | "calendar" | "workspace" | "outlook"

    Google Contacts is handled as a native tool in agent.py — not via Composio.
    Calendar — uses the explicit full tool list because the default
               toolkits=["googlecalendar"] only returns 20 of 40 tools.
    Outlook — uses a curated explicit list (16 tools from 200+).
    """
    if agent_type == "outlook":
        return _composio.tools.get(user_id=user_id, tools=_OUTLOOK_TOOLS)
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
    """Return connection status for Gmail, Google Calendar, and Outlook."""
    return {
        "gmail":    check_connection_status(user_id, "gmail"),
        "calendar": check_connection_status(user_id, "googlecalendar"),
        "outlook":  check_connection_status(user_id, "outlook"),
    }


def _auth_config_for(agent_type: str) -> str:
    """Return the correct Composio auth config ID for the given agent type."""
    if agent_type == "calendar":
        return settings.calendar_auth_config_id
    if agent_type == "outlook":
        return settings.outlook_auth_config_id
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
    if agent_type == "outlook":
        toolkit = "outlook"
    elif agent_type == "calendar":
        toolkit = "googlecalendar"
    else:
        toolkit = "gmail"
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


def get_user_profile(user_id: str, provider: str = "gmail") -> dict:
    """
    Fetch a rich user profile from the appropriate provider APIs in parallel.
    All sources run concurrently with a 10 s total timeout — a slow or
    failed source never blocks the others. Callers treat every key as optional.

    provider="gmail" (Google Workspace):
      - GMAIL_GET_PROFILE              → email, message/thread counts
      - GOOGLECALENDAR_SETTINGS_LIST   → timezone, locale, date/time format, week start
      - GOOGLECALENDAR_LIST_CALENDARS  → user's calendar list
      - GOOGLECONTACTS_LIST_CONTACTS   → frequent contacts
      - GOOGLECALENDAR_GET_CURRENT_DATE_TIME → current local date/time

    provider="outlook" (Microsoft 365):
      - OUTLOOK_GET_PROFILE            → email, display name
      - OUTLOOK_GET_MAILBOX_SETTINGS   → timezone, working hours, locale
      - OUTLOOK_LIST_CALENDARS         → user's calendar list
      - OUTLOOK_LIST_USER_CONTACTS     → frequent contacts
    """
    if provider == "outlook":
        return _get_user_profile_outlook(user_id)
    return _get_user_profile_gmail(user_id)


def _get_user_profile_gmail(user_id: str) -> dict:
    """Fetch profile from Google Workspace APIs."""
    profile: dict = {"provider": "gmail"}

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

    # Current datetime (needs timezone resolved above)
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


# ── Outlook profile fetchers ─────────────────────────────────────────────────

def _fetch_outlook_profile(user_id: str) -> dict:
    """Fetch Outlook profile metadata (displayName, email, jobTitle, etc.)."""
    result: dict = {}
    try:
        raw = execute_tool(user_id, "OUTLOOK_GET_PROFILE", {})
        data = json.loads(raw)
        if isinstance(data, dict):
            if data.get("mail") or data.get("userPrincipalName"):
                result["outlook_email"] = data.get("mail") or data.get("userPrincipalName", "")
            if data.get("displayName"):
                result["outlook_display_name"] = data["displayName"]
            if data.get("jobTitle"):
                result["job_title"] = data["jobTitle"]
            if data.get("officeLocation"):
                result["office_location"] = data["officeLocation"]
    except Exception:
        pass
    return result


def _windows_tz_to_iana(win_tz: str) -> str:
    """Best-effort mapping from Windows timezone names to IANA identifiers.

    Microsoft Graph returns Windows names (e.g. "India Standard Time").
    Agents and Python's zoneinfo need IANA names (e.g. "Asia/Kolkata").
    Falls back to the original string if no mapping is found — the system
    prompt still shows the user's timezone even if un-normalised.
    """
    _MAP = {
        "Dateline Standard Time":              "Etc/GMT+12",
        "UTC-11":                              "Pacific/Pago_Pago",
        "Hawaiian Standard Time":              "Pacific/Honolulu",
        "Alaskan Standard Time":               "America/Anchorage",
        "Pacific Standard Time":               "America/Los_Angeles",
        "US Mountain Standard Time":           "America/Phoenix",
        "Mountain Standard Time":              "America/Denver",
        "Central Standard Time":               "America/Chicago",
        "Eastern Standard Time":               "America/New_York",
        "US Eastern Standard Time":            "America/Indianapolis",
        "Atlantic Standard Time":              "America/Halifax",
        "Newfoundland Standard Time":          "America/St_Johns",
        "SA Eastern Standard Time":            "America/Cayenne",
        "E. South America Standard Time":      "America/Sao_Paulo",
        "UTC":                                 "UTC",
        "GMT Standard Time":                   "Europe/London",
        "W. Europe Standard Time":             "Europe/Berlin",
        "Central European Standard Time":      "Europe/Warsaw",
        "Romance Standard Time":               "Europe/Paris",
        "Central Europe Standard Time":        "Europe/Budapest",
        "E. Europe Standard Time":             "Europe/Chisinau",
        "FLE Standard Time":                   "Europe/Kiev",
        "GTB Standard Time":                   "Europe/Bucharest",
        "Russian Standard Time":               "Europe/Moscow",
        "Turkey Standard Time":                "Europe/Istanbul",
        "Israel Standard Time":                "Asia/Jerusalem",
        "South Africa Standard Time":          "Africa/Johannesburg",
        "Egypt Standard Time":                 "Africa/Cairo",
        "Arabic Standard Time":                "Asia/Baghdad",
        "Arab Standard Time":                  "Asia/Riyadh",
        "Iran Standard Time":                  "Asia/Tehran",
        "Arabian Standard Time":               "Asia/Dubai",
        "Azerbaijan Standard Time":            "Asia/Baku",
        "Afghanistan Standard Time":           "Asia/Kabul",
        "Pakistan Standard Time":              "Asia/Karachi",
        "West Asia Standard Time":             "Asia/Tashkent",
        "India Standard Time":                 "Asia/Kolkata",
        "Sri Lanka Standard Time":             "Asia/Colombo",
        "Nepal Standard Time":                 "Asia/Kathmandu",
        "Central Asia Standard Time":          "Asia/Almaty",
        "Bangladesh Standard Time":            "Asia/Dhaka",
        "Myanmar Standard Time":               "Asia/Yangon",
        "SE Asia Standard Time":               "Asia/Bangkok",
        "China Standard Time":                 "Asia/Shanghai",
        "Singapore Standard Time":             "Asia/Singapore",
        "W. Australia Standard Time":          "Australia/Perth",
        "Taipei Standard Time":                "Asia/Taipei",
        "Tokyo Standard Time":                 "Asia/Tokyo",
        "Korea Standard Time":                 "Asia/Seoul",
        "AUS Central Standard Time":           "Australia/Darwin",
        "Cen. Australia Standard Time":        "Australia/Adelaide",
        "AUS Eastern Standard Time":           "Australia/Sydney",
        "E. Australia Standard Time":          "Australia/Brisbane",
        "West Pacific Standard Time":          "Pacific/Port_Moresby",
        "Tasmania Standard Time":              "Australia/Hobart",
        "New Zealand Standard Time":           "Pacific/Auckland",
        "Fiji Standard Time":                  "Pacific/Fiji",
        "Samoa Standard Time":                 "Pacific/Apia",
    }
    return _MAP.get(win_tz, win_tz)


def _fetch_outlook_mailbox_settings(user_id: str) -> dict:
    """Fetch Outlook mailbox settings (timezone, working hours, locale, auto-replies)."""
    result: dict = {}
    try:
        raw = execute_tool(user_id, "OUTLOOK_GET_MAILBOX_SETTINGS", {})
        data = json.loads(raw)
        if isinstance(data, dict):
            # timezone — Graph returns Windows names; convert to IANA
            raw_tz = data.get("timeZone") or data.get("timezone") or ""
            if raw_tz:
                result["timezone"] = _windows_tz_to_iana(raw_tz)
                result["timezone_raw"] = raw_tz  # preserve original for reference
            # locale / language
            lang = data.get("language") or {}
            if isinstance(lang, dict):
                locale = lang.get("locale") or ""
                display_name = lang.get("displayName") or ""
                if locale:
                    result["locale"] = locale
                if display_name:
                    result["language"] = display_name
            elif isinstance(lang, str) and lang:
                result["locale"] = lang
            # working hours
            wh = data.get("workingHours") or {}
            if isinstance(wh, dict):
                days = wh.get("daysOfWeek", [])
                if days:
                    result["working_days"] = days
                start_time = wh.get("startTime") or ""
                end_time = wh.get("endTime") or ""
                if start_time and end_time:
                    result["working_hours"] = f"{start_time} – {end_time}"
                wh_tz = (wh.get("timeZone") or {})
                if isinstance(wh_tz, dict):
                    wh_tz_name = wh_tz.get("name") or ""
                    if wh_tz_name and not result.get("timezone"):
                        result["timezone"] = _windows_tz_to_iana(wh_tz_name)
                        result["timezone_raw"] = wh_tz_name
            # date/time format
            if data.get("dateFormat"):
                result["date_format"] = data["dateFormat"]
            if data.get("timeFormat"):
                result["time_format"] = data["timeFormat"]
    except Exception:
        pass
    return result


def _fetch_outlook_calendars(user_id: str) -> dict:
    """Fetch the user's Outlook calendar list."""
    result: dict = {}
    try:
        raw = execute_tool(user_id, "OUTLOOK_LIST_CALENDARS", {})
        data = json.loads(raw)
        items = data.get("value") or data.get("calendars") or (data if isinstance(data, list) else [])
        calendars = []
        for cal in items:
            if isinstance(cal, dict):
                entry = {
                    "name": cal.get("name") or cal.get("summary") or "",
                    "primary": cal.get("isDefaultCalendar") or cal.get("primary", False),
                    "id": cal.get("id") or "",
                    "color": cal.get("color") or "",
                    "can_edit": cal.get("canEdit", True),
                }
                if entry["name"] or entry["id"]:
                    calendars.append(entry)
        if calendars:
            result["calendars"] = calendars
    except Exception:
        pass
    return result


def _fetch_outlook_contacts(user_id: str) -> dict:
    """Fetch the user's Outlook contacts."""
    try:
        raw = execute_tool(user_id, "OUTLOOK_LIST_USER_CONTACTS", {})
        data = json.loads(raw)
        contacts_raw = (
            data.get("value")
            or data.get("contacts")
            or (data if isinstance(data, list) else [])
        )
        contacts = []
        for c in contacts_raw:
            if not isinstance(c, dict):
                continue
            name = c.get("displayName") or c.get("name") or ""
            # Outlook contacts have emailAddresses as a list of {name, address}
            email = ""
            email_addrs = c.get("emailAddresses") or []
            if isinstance(email_addrs, list) and email_addrs:
                first_email = email_addrs[0]
                if isinstance(first_email, dict):
                    email = first_email.get("address") or first_email.get("email") or ""
                elif isinstance(first_email, str):
                    email = first_email
            if not email:
                email = c.get("email") or c.get("emailAddress") or ""
            # Phone numbers
            phone = ""
            phones = c.get("mobilePhone") or ""
            if not phones:
                business_phones = c.get("businessPhones") or []
                if isinstance(business_phones, list) and business_phones:
                    phone = business_phones[0]
            else:
                phone = phones
            if email:
                entry: dict = {"name": name.strip(), "email": email.strip().lower()}
                if phone:
                    entry["phone"] = phone.strip()
                contacts.append(entry)
        if contacts:
            return {"frequent_contacts": contacts}
    except Exception:
        pass
    return {}


def _get_user_profile_outlook(user_id: str) -> dict:
    """Fetch profile from Microsoft 365 / Outlook APIs.

    Mailbox settings are fetched FIRST (blocking) so the resolved timezone
    is available before any other source needs it.  The remaining sources
    (profile, calendars, contacts) run in parallel afterwards.
    """
    profile: dict = {"provider": "outlook"}

    # Step 1 — fetch mailbox settings first to get the user's timezone
    try:
        mailbox = _fetch_outlook_mailbox_settings(user_id)
        profile.update(mailbox)
    except Exception:
        pass

    # Step 2 — fetch the remaining sources in parallel
    with ThreadPoolExecutor(max_workers=settings.profile_fetch_workers) as pool:
        futures = {
            "profile":   pool.submit(_fetch_outlook_profile, user_id),
            "calendars": pool.submit(_fetch_outlook_calendars, user_id),
            "contacts":  pool.submit(_fetch_outlook_contacts, user_id),
        }
        for key, future in futures.items():
            try:
                profile.update(future.result(timeout=settings.profile_fetch_timeout))
            except Exception:
                pass

    # Step 3 — compute current datetime in the user's resolved timezone
    tz_name = profile.get("timezone", "UTC")
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt
        user_now = _dt.now(ZoneInfo(tz_name))
        profile["current_datetime"] = user_now.strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        # Timezone unrecognised — fall back to UTC
        try:
            from datetime import datetime as _dt, timezone as _tz
            profile["current_datetime"] = _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M UTC")
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
