"""
Application-wide string constants and enumerations.

Configurable numeric limits live in app/config/settings.py.
Non-configurable labels, field names, and message templates belong here.
"""

# ── WhatsApp messages ─────────────────────────────────────────────────────────

WHATSAPP_TEST_MESSAGE = (
    "✅ Test message from AI Assistant — WhatsApp notifications are working!"
)
WHATSAPP_TEST_SEND_FAILED = (
    "Send failed — check Twilio credentials and sandbox activation"
)

# ── Trigger / webhook payload field names ────────────────────────────────────

# Gmail payload wrapper key (Composio may nest message data here)
GMAIL_PAYLOAD_WRAPPER = "messageData"

# Gmail fields extracted for toast/WA preview
GMAIL_FIELDS = ("from", "to", "subject", "snippet", "threadId", "messageId", "date")

# Calendar fields extracted for toast/WA preview
CALENDAR_FIELDS = (
    "summary", "title", "description", "location",
    "start", "end", "status", "htmlLink",
    "organizer", "attendees", "recurringEventId",
)

# Attendee-response-specific extra fields
ATTENDEE_RESPONSE_FIELDS = ("attendee", "response_status", "responseStatus")

# Starting-soon extra fields
STARTING_SOON_FIELDS = ("minutes_until_start", "minutesUntilStart")

# Calendar event wrapper key
CALENDAR_PAYLOAD_WRAPPER = "event"

# ── Speech recognition locale ─────────────────────────────────────────────────
# Used server-side if the backend ever needs locale-aware parsing.
SPEECH_LOCALE = "en-US"
