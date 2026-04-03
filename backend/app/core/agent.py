"""
Claude agentic loop with Composio tool execution, streamed via SSE.
Supports two subagents: Gmail and Google Calendar.
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator

import anthropic
import httpx

from .session_store import Session, session_store
from .composio_client import get_tools, execute_tool, email_to_user_id, get_user_profile
from .notifier import send_whatsapp
from .profile_store import save_profile
from .history_store import save_history
from ..config.settings import settings

logger = logging.getLogger(__name__)


def _is_gmail(email: str) -> bool:
    """Return True if the email address belongs to a Gmail / Google domain."""
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in ("gmail.com", "googlemail.com")


def _provider_for(email: str) -> str:
    """Return 'gmail' or 'outlook' based on the email domain."""
    return "gmail" if _is_gmail(email) else "outlook"


# How long a cached profile stays fresh before a background refresh is triggered
_PROFILE_TTL = timedelta(minutes=30)
# How long fetched tool schemas are reused before re-fetching from Composio
_TOOLS_TTL = timedelta(minutes=5)

# ── Module-level singletons ───────────────────────────────────────────────────
# Reuse a single AsyncAnthropic instance across all requests so its underlying
# httpx connection pool is shared (avoids per-request TCP handshake overhead).
_anthropic_client: anthropic.AsyncAnthropic | None = None

_ANTHROPIC_ERROR_LABELS: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized — check API key",
    403: "Forbidden",
    404: "Not Found",
    408: "Request Timeout",
    429: "Rate Limited — too many requests",
    500: "Anthropic Internal Server Error",
    529: "Anthropic Overloaded — service busy",
}

# TPM retry: on a tokens-per-minute 429, wait for the window to reset.
# SDK max_retries=0 disables useless within-window retries.
_TPM_RETRY_WAITS         = [60, 90]  # seconds: 1st retry, 2nd retry
_TPM_MAX_RETRIES         = 2

# Transient retry: 500/529/connection errors — short silent backoff.
_TRANSIENT_RETRY_WAIT_SECS = 2       # doubles each attempt: 2s, 4s, 6s
_TRANSIENT_MAX_RETRIES     = 3


def _is_tpm_rate_limit(exc: Exception) -> bool:
    """True when the 429 is caused by TPM (input tokens/min) exhaustion."""
    if not isinstance(exc, anthropic.APIStatusError) or exc.status_code != 429:
        return False
    try:
        msg = exc.body.get("error", {}).get("message", "") if isinstance(exc.body, dict) else ""
        return "tokens per minute" in msg.lower()
    except Exception:
        return False


def _is_transient_error(exc: Exception) -> bool:
    """True for 500/529/connection errors worth retrying with short backoff."""
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return True
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code in (500, 529):
        return True
    return False


def _format_api_error(exc: Exception) -> dict:
    """Return a structured {code, message} dict for any Anthropic/httpx exception."""
    if isinstance(exc, anthropic.APIStatusError):
        code = exc.status_code
        label = _ANTHROPIC_ERROR_LABELS.get(code, f"HTTP {code}")
        # Try to get the short message from the response body
        try:
            body_msg = exc.body.get("error", {}).get("message", "") if isinstance(exc.body, dict) else ""
        except Exception:
            body_msg = ""
        message = body_msg or label
        return {"error_code": str(code), "message": f"[{code}] {message}"}
    if isinstance(exc, anthropic.APITimeoutError):
        return {"error_code": "TIMEOUT", "message": "[TIMEOUT] Request timed out — please retry"}
    if isinstance(exc, anthropic.APIConnectionError):
        return {"error_code": "CONNECTION", "message": "[CONNECTION] Could not reach Anthropic API"}
    return {"error_code": "ERROR", "message": f"[ERROR] {exc}"}


def _get_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            max_retries=0,  # TPM retry loop below owns all waits; SDK retries fire within same window
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0),
        )
    return _anthropic_client


# Tool schema cache: key = "{user_id}:{agent_type}" → (tools_list, fetched_at)
# Tool definitions are stable between requests — caching avoids a Composio API
# call on every message while still picking up changes after the TTL expires.
_tools_cache: dict[str, tuple[list, datetime]] = {}


def evict_tools_cache(user_id: str) -> None:
    """Remove all cached tool entries for a user. Called on logout."""
    keys = [k for k in _tools_cache if k.startswith(f"{user_id}:")]
    for k in keys:
        del _tools_cache[k]


async def _get_tools_cached(user_id: str, agent_type: str) -> list:
    """Return Composio tools for the given user/agent, cached for _TOOLS_TTL.
    Retries up to 3 times with 2s/4s/6s backoff on transient Composio 500 errors.
    """
    cache_key = f"{user_id}:{agent_type}"
    entry = _tools_cache.get(cache_key)
    if entry is not None:
        tools, fetched_at = entry
        if datetime.utcnow() - fetched_at < _TOOLS_TTL:
            return tools
    last_exc = None
    for attempt in range(1, 4):  # up to 3 attempts
        try:
            tools = await asyncio.to_thread(get_tools, user_id, agent_type)
            _tools_cache[cache_key] = (tools, datetime.utcnow())
            return tools
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                await asyncio.sleep(attempt * 2)  # 2s, 4s
    raise last_exc

# ── System prompts ────────────────────────────────────────────────────────────

_SHARED_FORMATTING = """
## Response Formatting
- Use **bold** for names, subject lines, dates, and key values
- Use bullet points for lists of emails, events, or action items
- Use numbered lists for sequential steps or instructions
- Use markdown tables when comparing or displaying structured data
- Add a brief **Summary** line at the top when returning more than 3 items
- Keep responses concise — lead with the most important information
- End with a short follow-up offer when relevant

## Asking for Additional Information
When you need more details from the user to complete an action, always include a pre-filled example directly in your response so they can copy it, make quick edits, and reply — never ask for fields one at a time in plain prose.

List every required field as a labelled line inside a code block, pre-filled with a sensible illustrative value. Use only the fields relevant to the action; omit fields you already know. For attendee and recipient fields, always show the person's name alongside their email address — never a bare email alone.

For a **meeting / calendar event**:
```
Title:     Weekly Sync
Date:      Tomorrow at 3 pm
Duration:  30 minutes
Attendees: Alice Martin (alice.martin@example.com), Bob Singh (bob.singh@example.com)
Agenda:    Review sprint progress, blockers, next steps
```

For an **email**:
```
To:      Alice Martin (alice.martin@example.com)
Subject: Follow-up: Project Proposal
Body:    Hi Alice, just following up on the proposal we discussed...
```

For a **task or reminder**:
```
Title: Submit expense report
Due:   Friday at 5 pm
Notes: Include receipts from last week's travel
```

## WhatsApp Notifications

Use the single `send_whatsapp_message` tool for all WhatsApp communication:

**Sending to yourself** (`recipient_type='self'`):
- Use when the user says "send me a WhatsApp", "notify me on WhatsApp", "WhatsApp me a summary", or similar
- Send immediately without asking for confirmation — the registered number is used automatically
- If WhatsApp is not configured or disabled, tell the user to set it up via the **WA** button in the app header

**Sending to a contact** (`recipient_type='contact'`):
- Use when the user asks to WhatsApp a specific person (e.g. "WhatsApp John the meeting details")
- Always resolve the contact's phone number from Google Contacts using `GOOGLECONTACTS_*` tools first — do not ask the user for the number
- Once resolved, send immediately without further confirmation
- Phone number must be E.164 format (e.g. +447911123456); inform the user only if no number is found in their contacts
"""

GMAIL_SYSTEM_PROMPT = f"""You are a professional AI executive assistant specialising in Gmail inbox management.

## Capabilities

### Reading & Searching
- Read, search, and browse emails by sender, subject, label, date, or keyword
- Summarise email threads and individual messages
- Identify unread, flagged, urgent, or unanswered emails
- Show the most recent or most important messages from a sender or thread

### Composing & Replying
- Draft, send, and reply to professional emails
- Compose follow-up emails and re-engagement messages
- Forward emails with added context

### Inbox Organisation
- Label, archive, move, and delete emails
- Mark emails as read/unread or starred
- Help create filters and organise inbox structure
- Track pending replies and follow-ups

### Google Contacts
- Look up a contact by name, email address, or phone number
- List all contacts in the user's Google Contacts directory
- Retrieve full contact details including email addresses, phone numbers, and organisation
- Use contact data to auto-fill recipient email addresses when composing or replying

### Real-Time Notifications (Triggers)
The following Gmail events fire automatic notifications to the user's screen without any prompt needed:
- 📨 **New Email Received** — triggers instantly when a new message arrives in the inbox
- 📤 **Email Sent** — triggers when the authenticated user successfully sends a message

When the user asks to "turn on notifications", "enable alerts", or "notify me when I get email", inform them that these triggers can be activated via the notification settings panel and will show as pop-up toasts in the app.
{_SHARED_FORMATTING}
## Behaviour
- Before sending an email, confirm the recipient, subject, and key content with the user unless explicitly told to proceed
- When a recipient is specified by name only, first check the Frequent Contacts pre-loaded in the user profile; only if no match is found there, call the Composio `GOOGLECONTACTS_*` tool to resolve their email address
- When displaying emails, always show: sender, subject, date, and a one-line summary
- When scheduling a meeting or sending a calendar invite, use **30 minutes** as the default duration if the user has not specified one
- If a request is ambiguous, ask one clarifying question before acting
"""

CALENDAR_SYSTEM_PROMPT = f"""You are a professional AI executive assistant specialising in Google Calendar management.

## Capabilities

### Reading & Searching Events
- **List events** (`GOOGLECALENDAR_EVENTS_LIST`) — list events on a calendar within a time range; use timeMin/timeMax for date filtering; always pass `maxResults=20` (or higher if the user asks for more) — the API default is only 5; always use `GOOGLECALENDAR_GET_CURRENT_DATE_TIME` first to resolve relative dates like "this week" or "today"
- **Find event** (`GOOGLECALENDAR_FIND_EVENT`) — search events by text query, time range, or attendee
- **Get current date/time** (`GOOGLECALENDAR_GET_CURRENT_DATE_TIME`) — retrieve the current date and time in a given timezone; call this before any date-relative query

### Event Management
- **Create event** (`GOOGLECALENDAR_CREATE_EVENT`) — create a calendar event with title, start datetime, duration, timezone, location, description, and attendees; automatically adds a Google Meet link
- **Update event** (`GOOGLECALENDAR_UPDATE_EVENT`) — fully update an existing event by event ID (requires fetching the event first)
- **Patch event** (`GOOGLECALENDAR_PATCH_EVENT`) — partially update specific fields of an existing event; use to modify attendees or individual fields without rewriting the whole event
- **Delete event** (`GOOGLECALENDAR_DELETE_EVENT`) — permanently remove a specific event by its event ID

### Availability
- **Find free slots** (`GOOGLECALENDAR_FIND_FREE_SLOTS`) — find available time slots across one or more calendars

### Calendar Management
- **List calendars** (`GOOGLECALENDAR_LIST_CALENDARS`) — retrieve all calendars in the user's calendar list
- **Get calendar list entry** (`GOOGLECALENDAR_CALENDAR_LIST_GET`) — retrieve display settings for a specific calendar in the user's list

### Google Contacts
- **Search contacts** — find a contact by name, email, or phone number
- **List contacts** — retrieve all contacts from the user's Google Contacts directory
- **Get contact** — retrieve full details for a specific contact (email, phone, organisation)
- Use contact lookup to resolve a name to an email address when creating events or sending invites

### Real-Time Notifications (Triggers)
The following Google Calendar events fire automatic notifications to the user's screen without any prompt needed:
- ✅ **Event Created** — fires when a new calendar event is created
- ✏️ **Event Updated** — fires when an existing event is modified
- ❌ **Event Cancelled / Deleted** — fires when an event is cancelled or deleted
- 🔔 **Attendee Response Changed** — fires when any attendee's RSVP changes (accepted / declined / tentative)
- ⏰ **Event Starting Soon** — fires a configurable number of minutes before an event begins (default: 15 min)
- 🔄 **Calendar Event Sync** — full-sync polling trigger returning complete event data including attendees and metadata

When the user asks to "remind me before my next meeting", "notify me when someone RSVPs", or "alert me when my calendar changes", inform them that these triggers can be enabled via the notification settings panel.
{_SHARED_FORMATTING}
## Behaviour
- Always call `GOOGLECALENDAR_GET_CURRENT_DATE_TIME` first when the user uses relative dates ("today", "this week", "tomorrow", "next Monday")
- For listing events use `GOOGLECALENDAR_EVENTS_LIST` with timeMin/timeMax in ISO 8601 format with timezone; always pass `maxResults=20` (or higher if the user asks for more) — the API default is only 5
- Before creating an event, confirm title, date/time, duration, and attendees unless explicitly told to proceed
- When an attendee is specified by name only, first check the Frequent Contacts pre-loaded in the user profile; only if no match is found there, call the Composio `GOOGLECONTACTS_*` tool to resolve their email address
- For `GOOGLECALENDAR_CREATE_EVENT`, start_datetime must be ISO 8601 (e.g. `2025-06-10T14:00:00`) with an explicit timezone
- For update/patch operations, always retrieve the event first to get its event_id
- **Rescheduling conflicts — always confirm before acting:** When any conflict is detected and the resolution involves rescheduling an existing event, present the conflicting event details and your proposed new time, then wait for explicit user approval before calling any update/patch/delete tool. Never reschedule an existing event automatically.
- If a request is ambiguous, ask one clarifying question before acting
"""

WORKSPACE_SYSTEM_PROMPT = f"""You are a professional AI executive assistant for Google Workspace, with full access to Gmail, Google Calendar, and Google Contacts.

## Gmail Capabilities

### Reading & Searching
- Read, search, and browse emails by sender, subject, label, date, or keyword
- Summarise email threads and individual messages
- Identify unread, flagged, urgent, or unanswered emails

### Composing & Replying
- Draft, send, and reply to professional emails
- Compose follow-up emails, re-engagement messages, and forwards with added context

### Inbox Organisation
- Label, archive, move, and delete emails
- Mark emails as read/unread or starred; help create filters

## Google Calendar Capabilities

### Reading & Searching Events
- **List events** (`GOOGLECALENDAR_EVENTS_LIST`) — list events within a time range; use timeMin/timeMax; always pass `maxResults=20` (or higher if the user asks for more) — the API default is only 5; always call `GOOGLECALENDAR_GET_CURRENT_DATE_TIME` first for relative dates
- **Find event** (`GOOGLECALENDAR_FIND_EVENT`) — search by text, time range, or attendee

### Event Management
- Create, update, patch, and delete events; auto-add Google Meet links
- Modify attendees or individual fields using `GOOGLECALENDAR_PATCH_EVENT`

### Availability
- **Find free slots** (`GOOGLECALENDAR_FIND_FREE_SLOTS`)

### Calendar Management
- List and get calendars

## Google Contacts
- Look up contacts by name, email, or phone number
- Retrieve full details (email, phone, organisation)
- Use contact data to resolve names to email addresses for email composition and event invites

## Cross-Workspace Workflows
You excel at tasks that span Gmail and Calendar together, such as:
- Scheduling a meeting, sending the calendar invite, and emailing an agenda to attendees
- Checking calendar for free slots, then drafting an email to propose a time
- Finding an email about a meeting and creating a calendar event from its details
- Looking up attendee addresses from Contacts, inviting them to an event, and following up by email

## Tool Precedence

**Meeting / scheduling requests → always use Google Calendar tools first:**
- Any request to "book", "schedule", "set up", "arrange", or "create a meeting" must be handled with `GOOGLECALENDAR_CREATE_EVENT` — even if the user phrases it as "send a meeting email" or "email an invite".
- Use Gmail (e.g. `GMAIL_SEND_EMAIL`) only for the accompanying communication (agenda, follow-up, confirmation message) — never as the primary mechanism for creating the event itself.
- Decision rule: if the intent involves a time-blocked event on a calendar, reach for Calendar tools. If the intent is purely message delivery, reach for Gmail tools.

**Typical meeting booking sequence:**
1. Look up attendee email(s) via Composio `GOOGLECONTACTS_*` tools if given by name
2. Check availability with `GOOGLECALENDAR_FIND_FREE_SLOTS`
3. Create the event with `GOOGLECALENDAR_CREATE_EVENT` (include attendees — Google Calendar sends invites automatically)
4. Optionally send a personalised email with `GMAIL_SEND_EMAIL` only if the user asks for an additional message beyond the calendar invite

## Schedule & Meet / Schedule & Mail Workflow

Follow these stages whenever the user asks to schedule a meeting, set up a call, or send a meeting invite:

### Stage 1 — Gather Details
**Respond immediately with a text message — do NOT call any tools yet.**
Always open with a short line of text, then present the fillable template below so the user can edit it inline and click **Use this ↗** to send it back. Pre-fill any fields you already know from the request; leave the rest as illustrative placeholders.

Here's a quick template you can fill in:

```
Title:     Weekly Sync
Date:      Tomorrow at 3 pm
Duration:  30 minutes
Attendees: Alice Martin (alice.martin@example.com)
Agenda:    Discuss project updates and next steps
```

Wait for the user's filled-in response before calling any tools.

### Stage 2 — Check for Conflicts
Once the recipient and time are provided, check the calendar for any existing events at that slot.

**If no conflict:** Proceed directly to Stage 3.

**If there is a conflict:** Present the details of the conflicting event and ask the user to choose one of these options:
- **Option A — Reschedule the existing meeting first:** Suggest rescheduling the conflicting event to a nearby free slot, then schedule the new meeting in the original slot.
- **Option B — Proceed with the new meeting:** Go ahead and schedule the new meeting. Once sent, ask: Would you also like to cancel, reschedule, or make any changes to the conflicting meeting?

Wait for the user's choice before proceeding.

### Stage 3 — Draft & Send Invite
1. Look up the recipient's email from Frequent Contacts or Google Contacts.
2. Create a Google Meet link for the confirmed slot.
3. Suggest a default Meeting Title and Agenda for the user to review and modify.
4. Present the full draft invite and wait for confirmation.
5. Once confirmed, send the invite.

For **Schedule & Mail** requests, after sending the invite also draft and send a follow-up email with the agenda to all attendees using `GMAIL_SEND_EMAIL`.

{_SHARED_FORMATTING}
## Behaviour
- Always call `GOOGLECALENDAR_GET_CURRENT_DATE_TIME` first when the user uses relative dates ("today", "this week", "tomorrow", "next Monday")
- Before sending an email or creating a calendar event, confirm key details with the user unless explicitly told to proceed
- **Name → email resolution — always follow this priority order:**
  1. Check Frequent Contacts pre-loaded in the user profile (fastest, no API call)
  2. If not found, call `GOOGLECONTACTS_*` tools to search Google Contacts
  3. Only as a last resort, if the contact cannot be found in Google Contacts at all, may you use an email address seen in a calendar event attendee list — never infer or guess an email from a calendar entry if a Contacts lookup is still possible
  - Never use calendar attendee emails as the primary source for name-to-email mapping
- For `GOOGLECALENDAR_CREATE_EVENT`, start_datetime must be ISO 8601 (e.g. `2025-06-10T14:00:00`) with an explicit timezone
- For update/patch operations, always retrieve the event first to get its event_id
- **Rescheduling conflicts — always confirm before acting:** When any conflict is detected and the resolution involves rescheduling an existing event, present the conflicting event details and your proposed new time, then wait for explicit user approval before calling any update/patch/delete tool. Never reschedule an existing event automatically.
- When displaying emails, always show: sender, subject, date, and a one-line summary
- When scheduling a meeting or sending a calendar invite, use **30 minutes** as the default duration if the user has not specified one
- If a request is ambiguous, ask one clarifying question before acting
"""

OUTLOOK_SYSTEM_PROMPT = f"""You are a professional AI executive assistant for Microsoft Outlook, with full access to email, calendar, and contacts.

## Email Capabilities

### Reading & Searching
- List, read, and search emails by sender, subject, folder, date, or keyword using Outlook's KQL search syntax
- Summarise email threads (conversations) and individual messages
- Identify unread, flagged, urgent, or unanswered emails
- Show the most recent or most important messages from a sender or conversation
- Use `OUTLOOK_LIST_MESSAGES` to list messages in a folder (Inbox by default)
- Use `OUTLOOK_GET_MESSAGE` to retrieve a specific message by ID
- Use `OUTLOOK_SEARCH_MESSAGES` for powerful KQL-based search (from:, to:, subject:, received:, hasAttachment:, etc.)

### Composing & Replying
- Draft new emails with `OUTLOOK_CREATE_DRAFT`
- Send emails directly with `OUTLOOK_SEND_EMAIL`
- Send existing drafts with `OUTLOOK_SEND_DRAFT`
- Reply to messages with `OUTLOOK_CREATE_DRAFT_REPLY`
- Create forward drafts with `OUTLOOK_CREATE_FORWARD_DRAFT`
- Forward messages directly with `OUTLOOK_FORWARD_MESSAGE`

### Inbox Organisation
- Move messages between folders with `OUTLOOK_MOVE_MESSAGE`
- Delete messages with `OUTLOOK_DELETE_MESSAGE`
- Batch-update messages (mark read/unread, flag/unflag) with `OUTLOOK_BATCH_UPDATE_MESSAGES`
- Create new mail folders with `OUTLOOK_CREATE_MAIL_FOLDER`
- List all mail folders with `OUTLOOK_LIST_MAIL_FOLDERS`
- Outlook uses **folders** (Inbox, Sent Items, Drafts, Archive, etc.) instead of labels

## Calendar Capabilities

### Reading & Searching Events
- **Calendar view** (`OUTLOOK_GET_CALENDAR_VIEW`) — get all events active during a time window (includes multi-day events); use for "what's on my calendar today/this week" or availability checks
- **List events** (`OUTLOOK_LIST_EVENTS`) — retrieve events with filtering, pagination, sorting, and timezone support
- **Get event** (`OUTLOOK_GET_EVENT`) — retrieve full details of a specific event by ID
- **List calendars** (`OUTLOOK_LIST_CALENDARS`) — list all calendars in the user's mailbox

### Scheduling & Meeting Management
- **Create event** (`OUTLOOK_CALENDAR_CREATE_EVENT`) — create a new calendar event with title, start/end datetime, attendees, location, and description; pass `isOnlineMeeting: true` and `onlineMeetingProvider: "teamsForBusiness"` to auto-generate a Microsoft Teams meeting link
- **Update event** (`OUTLOOK_UPDATE_CALENDAR_EVENT`) — update specific fields of an existing event (reschedule, change attendees, modify details)
- **Delete event** (`OUTLOOK_DELETE_CALENDAR_EVENT`) — permanently remove an event
- **Cancel event** (`OUTLOOK_CANCEL_EVENT`) — cancel a meeting and send cancellation notifications to all attendees
- **Decline event** (`OUTLOOK_DECLINE_EVENT`) — decline a meeting invitation

### Conflict Detection & Availability
- **Find meeting times** (`OUTLOOK_FIND_MEETING_TIMES`) — suggest optimal meeting slots based on organizer and attendee availability, time constraints, and duration
- **Get schedule** (`OUTLOOK_GET_SCHEDULE`) — retrieve free/busy schedule for specified email addresses within a time window; use to check availability before scheduling

## Microsoft Contacts

- List all contacts with `OUTLOOK_LIST_USER_CONTACTS`
- Create a new contact with `OUTLOOK_CREATE_CONTACT` (name, email, phone, company, etc.)
- Update an existing contact with `OUTLOOK_UPDATE_CONTACT`
- Use contact data to auto-fill recipient email addresses when composing, replying, or creating calendar invites

## Profile & Settings

- Retrieve the user's Outlook profile with `OUTLOOK_GET_PROFILE`
- View mailbox settings (timezone, working hours, auto-replies) with `OUTLOOK_GET_MAILBOX_SETTINGS`
- Get drafts folder details with `OUTLOOK_GET_DRAFTS_MAIL_FOLDER`

{_SHARED_FORMATTING}
## Schedule & Meet Workflow

Follow these stages whenever the user asks to schedule a meeting, set up a call, or send a meeting invite:

### Stage 1 — Gather Details
**Respond immediately with a text message — do NOT call any tools yet.**
Always open with a short line of text, then present the fillable template below so the user can edit it inline and click **Use this ↗** to send it back. Pre-fill any fields you already know from the request; leave the rest as illustrative placeholders.

Here's a quick template you can fill in:

```
Title:     Weekly Sync
Date:      Tomorrow at 3 pm
Duration:  30 minutes
Attendees: Alice Martin (alice.martin@example.com)
Agenda:    Discuss project updates and next steps
```

Wait for the user's filled-in response before calling any tools.

### Stage 2 — Check for Conflicts
Once the recipient and time are provided, check the calendar for any existing events at that slot using `OUTLOOK_GET_CALENDAR_VIEW` or `OUTLOOK_GET_SCHEDULE`.

**If no conflict:** Proceed directly to Stage 3.

**If there is a conflict:** Present the details of the conflicting event and ask the user to choose one of these options:
- **Option A — Reschedule the existing meeting first:** Suggest rescheduling the conflicting event to a nearby free slot (use `OUTLOOK_FIND_MEETING_TIMES` to find one), then schedule the new meeting in the original slot.
- **Option B — Proceed with the new meeting:** Go ahead and schedule the new meeting. Once sent, ask: Would you also like to cancel, reschedule, or make any changes to the conflicting meeting?

Wait for the user's choice before proceeding.

### Stage 3 — Draft & Send Invite
1. Look up the recipient's email from Outlook Contacts via `OUTLOOK_LIST_USER_CONTACTS`.
2. Create the event with `OUTLOOK_CALENDAR_CREATE_EVENT` for the confirmed slot — always pass `isOnlineMeeting: true` and `onlineMeetingProvider: "teamsForBusiness"` to auto-generate a Microsoft Teams meeting link. Include attendees — Outlook sends invites automatically with the Teams join link embedded.
3. Suggest a default Meeting Title and Agenda for the user to review and modify.
4. Present the full draft invite and wait for confirmation.
5. Once confirmed, send the invite.

For **Schedule & Email** requests, after sending the invite also draft and send a follow-up email with the agenda to all attendees using `OUTLOOK_SEND_EMAIL`.

## Behaviour
- Before sending an email, confirm the recipient, subject, and key content with the user unless explicitly told to proceed
- When displaying emails, always show: sender, subject, date, and a one-line summary
- Outlook uses **folders** (not labels) for organisation — use folder-related tools accordingly
- Outlook uses **conversations** (not threads) — when fetching related messages, filter by conversationId via `OUTLOOK_LIST_MESSAGES`
- When the user asks to "organise", "clean up", or "sort" their inbox, suggest moving messages to appropriate folders
- Before creating a calendar event, confirm title, date/time, duration, and attendees unless explicitly told to proceed
- When scheduling a meeting, use **30 minutes** as the default duration if the user has not specified one
- **Always check for conflicts before scheduling:** Use `OUTLOOK_GET_CALENDAR_VIEW` or `OUTLOOK_GET_SCHEDULE` to check the proposed time slot before creating an event. If a conflict exists, present the details and ask the user how to proceed.
- **Rescheduling conflicts — always confirm before acting:** When any conflict is detected and the resolution involves rescheduling an existing event, present the conflicting event details and your proposed new time, then wait for explicit user approval before calling `OUTLOOK_UPDATE_CALENDAR_EVENT`. Never reschedule an existing event automatically.
- When an attendee is specified by name only, look up their email via `OUTLOOK_LIST_USER_CONTACTS` before creating an event or sending an invite
- For WhatsApp notifications, use the `send_whatsapp_message` tool with `recipient_type='self'`
- If a request is ambiguous, ask one clarifying question before acting
"""

_SYSTEM_PROMPTS: dict[str, str] = {
    "gmail":     GMAIL_SYSTEM_PROMPT,
    "calendar":  CALENDAR_SYSTEM_PROMPT,
    "workspace": WORKSPACE_SYSTEM_PROMPT,
    "outlook":   OUTLOOK_SYSTEM_PROMPT,
}

# ── Routing prompt ─────────────────────────────────────────────────────────────

_ROUTING_SYSTEM_PROMPT = """\
You are a routing classifier. Determine whether a user request is about \
email/Gmail or about scheduling/Google Calendar.

Respond with ONLY a valid JSON object on a single line — no other text:
{"agent": "gmail", "reason": "<one short sentence>"}
or
{"agent": "calendar", "reason": "<one short sentence>"}

Rules:
- "gmail" → reading, sending, searching, replying to or organising emails
- "calendar" → events, meetings, scheduling, reminders, availability, RSVPs
- When ambiguous (e.g. "schedule a meeting and email the invite"), choose "calendar"\
"""

# ── Context limits — driven by settings so they can be overridden via .env ────

_MAX_TOOL_RESULT_CHARS          = settings.max_tool_result_chars
_MAX_CALENDAR_TOOL_RESULT_CHARS = settings.calendar_tool_result_chars
_MAX_HISTORY_TURNS              = settings.max_history_turns

# Calendar event fields the LLM needs; everything else is stripped to save space
_CALENDAR_EVENT_KEEP_FIELDS = {
    "id", "summary", "description", "start", "end",
    "status", "location", "attendees", "organizer", "recurrence",
}
# Per-attendee fields to keep (attendee lists can be very large)
_CALENDAR_ATTENDEE_KEEP_FIELDS = {"email", "displayName", "responseStatus", "self"}

# ── Custom WhatsApp tool ───────────────────────────────────────────────────────

_WHATSAPP_TOOL = {
    "name": "send_whatsapp_message",
    "description": (
        "Send a WhatsApp message. Handles both cases:\n"
        "1. To the user themselves: set recipient_type='self' — sends to their registered number immediately, no confirmation needed.\n"
        "2. To a contact: set recipient_type='contact', look up their phone number from Google Contacts "
        "using GOOGLECONTACTS_* tools first, then call this tool with the resolved E.164 number. "
        "Always confirm the contact name and number with the user before sending to a contact."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The WhatsApp message text to send.",
            },
            "recipient_type": {
                "type": "string",
                "enum": ["self", "contact"],
                "description": "'self' to send to the user's own registered number; 'contact' to send to a specific contact.",
            },
            "phone_number": {
                "type": "string",
                "description": "Required when recipient_type='contact'. E.164 format (e.g. +447911123456), resolved from Google Contacts.",
            },
            "contact_name": {
                "type": "string",
                "description": "Display name of the contact — used for confirmation when recipient_type='contact'.",
            },
        },
        "required": ["message", "recipient_type"],
    },
}




# ── User profile block ────────────────────────────────────────────────────────

def _build_profile_block(email: str, display_name: str | None, profile: dict) -> str:
    """
    Build a system-prompt block from the user's pre-fetched profile.
    Automatically adapts to the provider (gmail vs outlook) based on the
    ``provider`` key in the profile dict.
    Every field is optional — missing keys are silently omitted.
    The agent reads this once on session start and must never ask the user for
    any information already present here.
    """
    provider = profile.get("provider", "gmail")
    is_outlook = provider == "outlook"

    lines = ["## User Profile (pre-loaded — never ask the user for this information)"]

    # ── Identity ──────────────────────────────────────────────────────────────
    lines.append("\n### Identity")
    lines.append(f"- **Email**: {email}")
    if display_name:
        lines.append(f"- **Name**: {display_name}")
    if is_outlook:
        if profile.get("outlook_display_name"):
            lines.append(f"- **Outlook display name**: {profile['outlook_display_name']}")
        if profile.get("job_title"):
            lines.append(f"- **Job title**: {profile['job_title']}")
        if profile.get("office_location"):
            lines.append(f"- **Office**: {profile['office_location']}")
    else:
        if profile.get("gmail_messages_total") is not None:
            lines.append(f"- **Total Gmail messages**: {profile['gmail_messages_total']:,}")
        if profile.get("gmail_threads_total") is not None:
            lines.append(f"- **Total Gmail threads**: {profile['gmail_threads_total']:,}")

    # ── Preferences ───────────────────────────────────────────────────────────
    tz = profile.get("timezone", "")
    prefs = []
    if tz:
        prefs.append(f"- **Timezone**: {tz}")
    if profile.get("current_datetime"):
        prefs.append(f"- **Current date/time**: {profile['current_datetime']}")
    if profile.get("locale"):
        prefs.append(f"- **Locale**: {profile['locale']}")
    if profile.get("language"):
        prefs.append(f"- **Language**: {profile['language']}")
    if profile.get("date_format"):
        prefs.append(f"- **Date format**: {profile['date_format']}")
    if profile.get("time_format"):
        prefs.append(f"- **Time format**: {profile['time_format']}")
    if not is_outlook:
        if profile.get("week_starts_on"):
            prefs.append(f"- **Week starts on**: {profile['week_starts_on']}")
        if profile.get("default_event_length_mins"):
            prefs.append(f"- **Default event duration**: {profile['default_event_length_mins']} minutes")
    if is_outlook:
        if profile.get("working_days"):
            days = profile["working_days"]
            days_str = ", ".join(days) if isinstance(days, list) else str(days)
            prefs.append(f"- **Working days**: {days_str}")
        if profile.get("working_hours"):
            prefs.append(f"- **Working hours**: {profile['working_hours']}")

    if prefs:
        lines.append("\n### Preferences")
        lines.extend(prefs)

    # ── Calendars ─────────────────────────────────────────────────────────────
    calendars: list[dict] = profile.get("calendars", [])
    if calendars:
        lines.append("\n### Calendars")
        for cal in calendars:
            if is_outlook:
                marker = " *(default)*" if cal.get("primary") else ""
                edit_flag = " [read-only]" if not cal.get("can_edit", True) else ""
                lines.append(f"- {cal['name']}{marker}{edit_flag}")
            else:
                marker = " *(primary)*" if cal.get("primary") else ""
                role = f" [{cal['access_role']}]" if cal.get("access_role") else ""
                lines.append(f"- {cal['name']}{marker}{role}")

    # ── Frequent contacts ──────────────────────────────────────────────────────
    frequent = profile.get("frequent_contacts", [])
    if frequent:
        source = "Outlook Contacts" if is_outlook else "Google Contacts"
        lines.append(f"\n### Frequent Contacts (from {source})")
        for c in frequent:
            name_part = f"{c['name']} " if c.get("name") else ""
            phone_part = f" · {c['phone']}" if c.get("phone") else ""
            lines.append(f"- {name_part}<{c['email']}>{phone_part}")

    # ── Standing instructions ─────────────────────────────────────────────────
    if is_outlook:
        lines.append(
            "\n**Instructions**: Use all profile information above directly — never ask "
            "the user to confirm timezone, name, calendar, contact, or frequent-contact details "
            "already listed. When the user refers to someone by first name, check Frequent Contacts "
            "first — only call `OUTLOOK_LIST_USER_CONTACTS` if no match is found there."
        )
    else:
        lines.append(
            "\n**Instructions**: Use all profile information above directly — never ask "
            "the user to confirm timezone, name, calendar, contact, or frequent-contact details "
            "already listed. When the user refers to someone by first name, check Frequent Contacts "
            "first — only call the Composio `GOOGLECONTACTS_*` tool if no match is found there."
        )
    if tz:
        lines.append(f"All dates and times must use the `{tz}` timezone.")

    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_content(content_blocks) -> list[dict]:
    """
    Convert Anthropic content blocks to plain dicts for re-use in subsequent
    API calls. Thinking blocks are intentionally excluded.
    """
    result = []
    for b in content_blocks:
        if b.type == "text":
            result.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": b.id,
                "name": b.name,
                "input": b.input,
            })
        # thinking blocks deliberately omitted
    return result


def _strip_calendar_event(event: dict) -> dict:
    """Return a minimal calendar event dict keeping only fields the LLM needs."""
    slim: dict = {}
    for k in _CALENDAR_EVENT_KEEP_FIELDS:
        if k in event:
            slim[k] = event[k]
    # Truncate description
    if isinstance(slim.get("description"), str) and len(slim["description"]) > 200:
        slim["description"] = slim["description"][:200] + "… [truncated]"
    # Strip attendees to essential fields only
    if isinstance(slim.get("attendees"), list):
        slim["attendees"] = [
            {f: a[f] for f in _CALENDAR_ATTENDEE_KEEP_FIELDS if f in a}
            for a in slim["attendees"]
        ]
    return slim


def _truncate_tool_result(result_str: str) -> str:
    """Truncate oversized tool results to avoid context overflow."""
    if len(result_str) <= _MAX_TOOL_RESULT_CHARS:
        return result_str
    try:
        data = json.loads(result_str)

        # ── Gmail: truncate long email body fields ─────────────────────────
        if isinstance(data, dict) and "messages" in data:
            for msg in data["messages"]:
                for key in ("messageText", "body", "snippet"):
                    _limit = settings.email_body_truncate_chars
                    if key in msg and isinstance(msg[key], str) and len(msg[key]) > _limit:
                        msg[key] = msg[key][:_limit] + "… [truncated]"
            truncated = json.dumps(data)
            if len(truncated) <= _MAX_TOOL_RESULT_CHARS:
                return truncated

        # ── Calendar: strip to essential fields, then apply higher size cap ─
        items_key = None
        if isinstance(data, dict):
            for k in ("items", "events", "data"):
                if k in data and isinstance(data[k], list):
                    items_key = k
                    break
        if items_key:
            data[items_key] = [_strip_calendar_event(e) for e in data[items_key]
                               if isinstance(e, dict)]
            truncated = json.dumps(data)
            if len(truncated) <= _MAX_CALENDAR_TOOL_RESULT_CHARS:
                return truncated
            # Still over the calendar cap — return as many complete events as fit
            kept: list = []
            for event in data[items_key]:
                candidate = {**data, items_key: kept + [event]}
                if len(json.dumps(candidate)) > _MAX_CALENDAR_TOOL_RESULT_CHARS:
                    break
                kept.append(event)
            data[items_key] = kept
            return json.dumps(data)

    except Exception:
        pass
    return result_str[:_MAX_TOOL_RESULT_CHARS] + "… [truncated]"


def _trim_history(messages: list[dict]) -> list[dict]:
    """Keep the most recent N turns to prevent context overflow."""
    if len(messages) <= _MAX_HISTORY_TURNS * 2:
        return messages
    return messages[-(_MAX_HISTORY_TURNS * 2):]


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ── Post-response suggestion generator ────────────────────────────────────────

def _extract_last_assistant_text(messages: list[dict]) -> str:
    """Pull the plain text from the most recent assistant turn."""
    for m in reversed(messages):
        if m.get("role") != "assistant":
            continue
        content = m.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block["text"]
    return ""


async def _generate_suggestions(
    client: anthropic.AsyncAnthropic,
    messages: list[dict],
    agent_type: str,
    user_profile: dict,
) -> list[str]:
    """
    Lightweight Haiku call that reads the last assistant response and returns
    0–3 specific, actionable follow-up chip strings. Returns [] when no clear
    next step exists or on any error.
    """
    last_response = _extract_last_assistant_text(messages)
    if not last_response:
        return []

    tz = user_profile.get("timezone", "UTC")

    prompt = (
        f"You generate follow-up action chips for a {agent_type} AI assistant UI.\n"
        f"User's timezone: {tz}\n\n"
        "Last assistant response:\n"
        f"{last_response[:settings.suggestion_context_chars]}\n\n"
        "Generate 0–3 short, specific follow-up chips the user would click next.\n"
        "Rules:\n"
        "- Output ONLY a raw JSON array — no markdown, no explanation\n"
        "- Each chip must be 6 words or fewer\n"
        "- Be specific: use real names, dates, times from the response\n"
        "- Return [] for summaries, greetings, or open-ended questions\n"
        "- Return [] if the assistant is waiting for user input\n"
        "Good: [\"Reply to Sarah\", \"Archive thread\"]\n"
        "Good: [\"Schedule Mon 10am\", \"Add Zoom link\"]\n"
        "Bad:  [\"Take action\", \"Proceed\", \"Continue\"]\n"
    )
    try:
        response = await client.messages.create(
            model=settings.suggestions_model_name,
            max_tokens=settings.suggestion_max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "[]")
        # Strip markdown code fences if Haiku wraps the JSON
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1]
            stripped = stripped.rsplit("```", 1)[0]
        items = json.loads(stripped.strip())
        if isinstance(items, list):
            return [s for s in items if isinstance(s, str)][:3]
    except Exception:
        pass
    return []


# ── Session preloading ────────────────────────────────────────────────────────

async def preload_session(email: str) -> None:
    """
    Eagerly warm up a session at auth time so the first chat message
    pays no profile-fetch or system-prompt-build cost.

    Fetches the user profile, then pre-builds and caches the system prompt
    for all three agents. Safe to call multiple times — a no-op if the
    profile was fetched within _PROFILE_TTL.
    """
    session = session_store.get_or_create(email)
    now = datetime.utcnow()

    # Skip if still fresh
    if (
        session.profile_fetched_at is not None
        and now - session.profile_fetched_at < _PROFILE_TTL
        and session.user_profile
    ):
        return

    user_id = email_to_user_id(email)
    provider = _provider_for(email)

    try:
        profile = await asyncio.to_thread(get_user_profile, user_id, provider)
        session.user_profile = profile
        session.profile_fetched_at = now
        session_store.update(session)
        save_profile(email, session.display_name, profile, provider)
        logger.info("preload_session: %s profile loaded and persisted for %s", provider, email)
    except Exception as exc:
        logger.warning("preload_session: profile fetch failed for %s: %s", email, exc)
        return

    # Pre-build system prompts for all agents
    for agent_type in ("gmail", "calendar", "workspace", "outlook"):
        if session.get_system_prompt(agent_type) is not None:
            continue  # already cached
        base_prompt = _SYSTEM_PROMPTS.get(agent_type, GMAIL_SYSTEM_PROMPT)
        profile_block = _build_profile_block(session.email, session.display_name, profile)
        session.set_system_prompt(agent_type, f"{base_prompt}\n\n{profile_block}")

    session_store.update(session)
    logger.info("preload_session: system prompts cached for %s", email)


# ── Main agentic loop ─────────────────────────────────────────────────────────

async def stream_agent_response(
    session: Session,
    user_message: str,
    agent_type: str = "gmail",
) -> AsyncGenerator[str, None]:
    """
    Run the Claude + Composio agentic loop for the given agent type,
    yielding SSE events.

    agent_type: "gmail" | "calendar" | "workspace"

    SSE event shapes:
      {"type": "text",       "content": "<delta>"}
      {"type": "tool_start", "name": "<action>", "display": "<label>"}
      {"type": "tool_end",   "name": "<action>", "success": true|false}
      {"type": "done"}
      {"type": "error",      "message": "<msg>"}
    """
    client = _get_client()
    composio_user_id = email_to_user_id(session.email)
    base_prompt = _SYSTEM_PROMPTS.get(agent_type, OUTLOOK_SYSTEM_PROMPT if agent_type == "outlook" else GMAIL_SYSTEM_PROMPT)

    try:
        tools = await _get_tools_cached(composio_user_id, agent_type)
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Could not load tools: {exc}"})
        return

    # Inject native tools — available to all agents regardless of Composio toolkit.
    tools = tools + [_WHATSAPP_TOOL]

    # Use preloaded system prompt if available; otherwise build it now (fallback)
    provider = _provider_for(session.email)
    system_prompt = session.get_system_prompt(agent_type)
    if system_prompt is None:
        if not session.user_profile:
            try:
                session.user_profile = await asyncio.to_thread(
                    get_user_profile, composio_user_id, provider
                )
                session.profile_fetched_at = datetime.utcnow()
                save_profile(session.email, session.display_name, session.user_profile, provider)
            except Exception:
                pass
        profile_block = _build_profile_block(
            session.email, session.display_name, session.user_profile
        )
        system_prompt = f"{base_prompt}\n\n{profile_block}"
        session.set_system_prompt(agent_type, system_prompt)
        session_store.update(session)
    else:
        # Trigger a background profile refresh if TTL has expired,
        # without blocking the current request.
        now = datetime.utcnow()
        if (
            session.profile_fetched_at is None
            or now - session.profile_fetched_at >= _PROFILE_TTL
        ):
            asyncio.create_task(preload_session(session.email))

    # Inject current datetime so agents always have a fresh timestamp
    # regardless of when the system prompt was originally built.
    tz = session.user_profile.get("timezone", "UTC")
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    dynamic_system = f"{system_prompt}\n\n**Current date/time**: {now_str} (timezone: {tz})"

    # Append user message to the correct history
    messages = session.get_messages(agent_type)
    messages.append({"role": "user", "content": user_message})
    session.set_messages(agent_type, messages)
    session_store.update(session)

    tpm_retries       = 0
    transient_retries = 0
    while True:
        history = _trim_history(session.get_messages(agent_type))
        _est_chars = (
            sum(len(json.dumps(m)) for m in history)
            + len(dynamic_system)
            + sum(len(json.dumps(t)) for t in tools)
        )
        print(
            f"[PRE-CALL] agent={agent_type} history_msgs={len(history)} "
            f"est_chars={_est_chars} est_tokens~={_est_chars // 4}",
            flush=True,
        )
        try:
            async with client.messages.stream(
                model=settings.model_name,
                max_tokens=settings.agent_max_tokens,
                system=dynamic_system,
                tools=tools,
                messages=history,
            ) as stream:
                async for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and event.delta.type == "text_delta"
                        and event.delta.text
                    ):
                        yield _sse({"type": "text", "content": event.delta.text})

                final_message = await stream.get_final_message()
                usage = final_message.usage
                print(
                    f"[TOKEN USAGE] agent={agent_type} loop_iter={tpm_retries} "
                    f"input={usage.input_tokens} output={usage.output_tokens} "
                    f"total={usage.input_tokens + usage.output_tokens}",
                    flush=True,
                )
                tpm_retries = 0
                transient_retries = 0

        except anthropic.APIError as exc:
            if _is_tpm_rate_limit(exc) and tpm_retries < _TPM_MAX_RETRIES:
                tpm_retries += 1
                wait = _TPM_RETRY_WAITS[tpm_retries - 1]  # 60s, then 90s
                yield _sse({
                    "type": "text",
                    "content": (
                        f"\n\n⏳ Rate limit reached (input tokens/min). "
                        f"Waiting {wait}s before retry {tpm_retries}/{_TPM_MAX_RETRIES}…\n\n"
                    ),
                })
                await asyncio.sleep(wait)
                continue
            if _is_transient_error(exc) and transient_retries < _TRANSIENT_MAX_RETRIES:
                transient_retries += 1
                await asyncio.sleep(_TRANSIENT_RETRY_WAIT_SECS * transient_retries)
                continue
            err = _format_api_error(exc)
            yield _sse({"type": "error", **err})
            return

        # Append assistant response to this agent's history
        current = session.get_messages(agent_type)
        current.append({
            "role": "assistant",
            "content": _serialize_content(final_message.content),
        })
        session.set_messages(agent_type, current)
        session_store.update(session)

        if final_message.stop_reason != "tool_use":
            break

        tool_uses = [b for b in final_message.content if b.type == "tool_use"]
        tool_results = []

        # Announce all tools before any execution so the UI shows them immediately
        for tu in tool_uses:
            display = tu.name.replace("_", " ").title()
            yield _sse({"type": "tool_start", "name": tu.name, "display": display})

        async def _execute_one(tu) -> str:
            """Run a single tool call and return the result string."""
            if tu.name == "send_whatsapp_message":
                message = tu.input.get("message", "")
                recipient_type = tu.input.get("recipient_type", "self")

                if recipient_type == "self":
                    if not session.whatsapp_number or not session.wa_notifications_enabled:
                        return json.dumps({
                            "error": (
                                "WhatsApp is not configured or is disabled for this user. "
                                "Ask the user to open the WA settings panel in the app header, "
                                "enter their phone number, enable notifications, and save."
                            )
                        })
                    ok, err = await send_whatsapp(session.whatsapp_number, message)
                    return json.dumps(
                        {"success": True, "sent_to": "self", "phone": session.whatsapp_number}
                        if ok else
                        {"error": err or "Failed to send WhatsApp message. Check Twilio credentials and sandbox activation."}
                    )
                else:
                    phone = tu.input.get("phone_number", "").strip()
                    contact_name = tu.input.get("contact_name", phone)
                    if not phone:
                        return json.dumps({"error": "phone_number is required for recipient_type='contact'. Look up the contact's number from Google Contacts first."})
                    ok, err = await send_whatsapp(phone, message)
                    return json.dumps(
                        {"success": True, "sent_to": contact_name, "phone": phone}
                        if ok else
                        {"error": err or f"Failed to send WhatsApp to {contact_name}. Check Twilio credentials and that the number has opted in to the sandbox."}
                    )

            result = await asyncio.to_thread(
                execute_tool, composio_user_id, tu.name, tu.input
            )
            return _truncate_tool_result(result)

        # Execute all tools concurrently — dramatically faster when Claude calls
        # multiple tools in one turn (e.g. get current time + list events).
        results = await asyncio.gather(*[_execute_one(tu) for tu in tool_uses])

        for tu, result_str in zip(tool_uses, results):
            success = True
            try:
                parsed = json.loads(result_str)
                if isinstance(parsed, dict) and parsed.get("error"):
                    success = False
            except Exception:
                pass

            yield _sse({"type": "tool_end", "name": tu.name, "success": success})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_str,
            })

        current = session.get_messages(agent_type)
        current.append({"role": "user", "content": tool_results})
        session.set_messages(agent_type, current)
        session_store.update(session)

    # Post-response: generate follow-up suggestions via Haiku.
    # Cap at 2.5 s — a slow Haiku call must not delay the "done" event for the user.
    try:
        suggestions = await asyncio.wait_for(
            _generate_suggestions(
                client, session.get_messages(agent_type), agent_type, session.user_profile
            ),
            timeout=2.5,
        )
    except (asyncio.TimeoutError, Exception):
        suggestions = []
    if suggestions:
        yield _sse({"type": "suggestions", "items": suggestions})

    # Persist conversation history so context survives backend restarts
    save_history(session.email, agent_type, session.get_messages(agent_type))

    yield _sse({"type": "done"})


# ── Core (goal/orchestrator) agent ────────────────────────────────────────────

async def _route_to_agent(user_message: str) -> tuple[str, str]:
    """
    Classify a user message as 'gmail' or 'calendar'.
    Returns (agent_type, reason).
    Falls back to 'gmail' on any error.
    Uses Haiku — routing is a simple binary classification that doesn't
    warrant a full Sonnet call.
    """
    client = _get_client()
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            system=_ROUTING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        data = json.loads(text.strip())
        agent = data.get("agent", "gmail")
        if agent not in ("gmail", "calendar"):
            agent = "gmail"
        return agent, data.get("reason", "")
    except Exception:
        return "gmail", "Default routing"


async def stream_core_agent_response(
    session: Session,
    user_message: str,
) -> AsyncGenerator[str, None]:
    """
    Orchestrator: classify the request → emit agent_routed → delegate to subagent.
    All SSE events from the subagent are forwarded verbatim.
    """
    agent_type, reason = await _route_to_agent(user_message)
    yield _sse({"type": "agent_routed", "agent": agent_type, "reason": reason})
    async for chunk in stream_agent_response(session, user_message, agent_type):
        yield chunk
