"""
Email Summarizer Agent
======================

Triggered on returning login.  Fetches unread emails, extracts actionable
items with Claude, then creates a Gmail draft.

Mode (EMAIL_SUMMARIZER_MODE)
----------------------------
  off     — feature completely disabled
  always  — runs on every login, no deduplication
  smart   — tracks processed email message IDs in TinyDB per user;
            only runs when there are unread emails not yet summarized

TinyDB schema (smart mode)
--------------------------
  { "email": "user@example.com", "processed_ids": ["gmailId1", ...] }

Notification
------------
Publishes an event to trigger_store on completion so the frontend receives
a TriggerToast and a system message in the chat window.
"""

import asyncio
import logging
import json
import re
import uuid
from datetime import date, datetime, timedelta

import anthropic
import httpx
from tinydb import TinyDB, Query

from .composio_client import execute_tool, email_to_user_id
from .trigger_store import publish
from .notifier import send_whatsapp
from .session_store import session_store
from ..config.settings import settings

logger = logging.getLogger(__name__)

# ── TinyDB setup ─────────────────────────────────────────────────────────────
_DB_PATH = settings.email_summarizer_db_path
_db: TinyDB | None = None
_User = Query()


def _get_db() -> TinyDB:
    global _db
    if _db is None:
        import os
        os.makedirs("data", exist_ok=True)
        _db = TinyDB(_DB_PATH)
    return _db


def get_processed_ids(email: str) -> set[str]:
    """Return the set of Gmail message IDs already summarized for this user."""
    record = _get_db().get(_User.email == email)
    if record is None:
        return set()
    return set(record.get("processed_ids", []))


def mark_ids_processed(email: str, new_ids: list[str]) -> None:
    """Add new_ids to the user's processed set in TinyDB."""
    db = _get_db()
    existing = get_processed_ids(email)
    merged = list(existing | set(new_ids))
    if db.get(_User.email == email):
        db.update({"processed_ids": merged}, _User.email == email)
    else:
        db.insert({"email": email, "processed_ids": merged})


def reset_processed_ids(email: str) -> bool:
    """Remove the user's tracking record entirely (used by the reset endpoint)."""
    removed = _get_db().remove(_User.email == email)
    return bool(removed)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_messages(raw_result: str) -> list[dict]:
    """Parse the Composio tool result into a list of message dicts."""
    data = json.loads(raw_result)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return (
            data.get("messages")
            or data.get("emails")
            or data.get("data", {}).get("messages", [])
            or []
        )
    return []


def _msg_id(msg: dict) -> str:
    """Extract the Gmail message ID from a message dict."""
    return (
        msg.get("id")
        or msg.get("messageId")
        or msg.get("message_id")
        or msg.get("threadId")
        or ""
    )


def _format_emails(messages: list[dict]) -> str:
    """Convert message dicts into readable text for Claude.

    Includes Gmail metadata (labels, category, importance) so the prompt
    can use Gmail's own signals as a pre-filter before inclusion/exclusion rules.
    Body priority: body_plain → body → snippet (snippet is a ~100-char preview
    that cuts off sign-offs; always prefer the full body when available).
    """
    lines: list[str] = []
    for i, msg in enumerate(messages, 1):
        sender  = msg.get("from") or msg.get("sender") or msg.get("From", "Unknown")
        subject = msg.get("subject") or msg.get("Subject", "(no subject)")

        # Full body preferred over Gmail's truncated snippet
        body = (
            msg.get("body_plain")
            or msg.get("body")
            or msg.get("snippet")
            or ""
        )
        if isinstance(body, str):
            body = body[:settings.email_summarizer_body_chars]

        # Gmail metadata — labels reveal category and importance signals
        raw_labels = msg.get("label_ids") or msg.get("labels") or []
        if isinstance(raw_labels, list):
            gmail_labels = ", ".join(raw_labels) if raw_labels else "none"
        else:
            gmail_labels = str(raw_labels)

        is_important = any(
            lbl in ("IMPORTANT", "STARRED")
            for lbl in (raw_labels if isinstance(raw_labels, list) else [])
        )
        category = next(
            (lbl for lbl in (raw_labels if isinstance(raw_labels, list) else [])
             if lbl.startswith("CATEGORY_")),
            "CATEGORY_UNKNOWN"
        )

        lines.append(
            f"Email {i}:\n"
            f"  From: {sender}\n"
            f"  Subject: {subject}\n"
            f"  Gmail-Labels: {gmail_labels}\n"
            f"  Gmail-Category: {category}\n"
            f"  Gmail-Important: {'yes' if is_important else 'no'}\n"
            f"  Body: {body}\n"
        )
    return "\n".join(lines)


# ── Rule summaries (shown in the chat system message) ────────────────────────

INCLUSION_RULE_SUMMARY = (
    "Emails sent by a real person or that require a direct response to a human, "
    "received in the last 2 weeks."
)

EXCLUSION_RULE_SUMMARY = (
    "Skipped only when clearly machine-origin: no-reply/donotreply sender addresses, "
    "bare OTP/password-reset emails, and transaction receipts with an order ID + amount "
    "but no human request."
)

# ── Core agent logic ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an executive assistant that extracts actionable items from emails.
Each email is provided with Gmail metadata (Gmail-Labels, Gmail-Category, \
Gmail-Important) in addition to the sender, subject, and body.

Process each email through the three steps below IN ORDER. Stop at the first \
step that makes a decision.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — Gmail signal pre-filter
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use Gmail's own metadata as the first signal before reading the content:

IMMEDIATE INCLUDE (go straight to output, skip Steps 2 & 3):
- Gmail-Important: yes  →  Gmail already flagged this as important; always include.
- Gmail-Category is CATEGORY_PERSONAL  →  Gmail classified it as personal; always include.
- Gmail-Labels contains STARRED  →  user starred it; always include.

LEAN EXCLUDE (proceed to Step 2 to confirm — do NOT exclude solely on this):
- Gmail-Category is CATEGORY_PROMOTIONS  →  likely marketing; still check Step 2.
- Gmail-Category is CATEGORY_SOCIAL  →  likely social notification; still check Step 2.

NEUTRAL (proceed to Step 2):
- Gmail-Category is CATEGORY_UPDATES, CATEGORY_FORUMS, CATEGORY_UNKNOWN, or none.
- Gmail-Important: no with no category signal.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — Inclusion rule (overrides Step 1 LEAN EXCLUDE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Include the email if ANY ONE of the following is true in the sender or body:
- Sender is a personal address: @gmail.com, @yahoo.com, @outlook.com, \
@hotmail.com, @icloud.com, or clearly a named individual's work address.
- Body contains a human sign-off: Regards, Thanks, Best, Cheers, Sincerely, \
Warm regards, etc.
- Body contains a list of tasks, action items, or reminders directed at the reader \
— regardless of formatting (# headings, bullets, numbered lists).
- Subject or body explicitly asks the reader to do something or reply.

One match is enough — do NOT require multiple signals.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — Exclusion rule (last resort — narrow)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Exclude ONLY when ALL signals for one of these three patterns are unambiguously present:
1. Sender address contains "noreply", "no-reply", "donotreply", "mailer-daemon", \
or "postmaster" — AND the body contains no human sign-off and no personal ask.
2. Email contains a one-time code, reset link, or OTP as its sole purpose \
(password reset / 2FA — not merely mentioned in passing).
3. Financial transaction receipt: subject starts with "Receipt"/"Invoice"/"Order \
confirmation" AND body contains a currency symbol + amount AND no question or \
request directed at the reader.

Do NOT exclude based on tone, formatting style, subject keywords, or category guesses.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Actionable Items
Produce this table for every email that passed Steps 1 or 2:

| # | Priority | Action Required | From | Sender Email | Subject | Email Count |
|---|----------|----------------|------|--------------|---------|-------------|

- **Priority**: 🔴 Urgent · 🟡 Soon · 🟢 Low
  - 🔴 if: explicit deadline/date, words like "urgent/ASAP/by EOD", high-seniority sender, \
financial or legal matter requiring response
  - 🟡 if: clear ask with no stated deadline, follow-up needed within a week
  - 🟢 if: informational with a soft ask, no time pressure
- **Action Required**: concise verb phrase — e.g. "Reply with Q1 budget figures", \
"Schedule demo", "File advance tax return", "Book medical appointment"
- **From**: display name only; if only an email address is available, use the part \
before the @ symbol (e.g. "sksrrr23" from sksrrr23@gmail.com)
- **Sender Email**: the full sender email address (e.g. sksrrr23@gmail.com); use "—" \
if no email address is available
- **Subject**: truncated to 50 chars if needed; replace any `|` characters in cell \
values with `/` to avoid breaking the table
- **Email Count**: number of emails that contributed to this action item. If the row \
was NOT merged during deduplication, write 1. If multiple emails were merged into this \
row, write the count of merged emails (e.g. 3).

**Deduplication — apply before finalising the table:**
After drafting all candidate rows, merge rows that represent the same underlying task:
- Two rows are duplicates if their **Action Required** describes the same real-world task \
(e.g. "Schedule a call with Priya" and "Book call with Priya re: Q2"), regardless of \
minor wording differences or which email they came from.
- Keep only the single highest-priority row for the merged group.
- If the merged group spans multiple senders or subjects, keep the From/Subject of the \
highest-priority email; ignore the rest.
- Set Email Count to the total number of emails merged into the row.
- Do NOT merge rows that require separate responses to different people, even if the verb \
is similar (e.g. "Reply to Alice re: budget" and "Reply to Bob re: budget" are distinct).

Sort rows: 🔴 first, 🟢 last.

If no actionable emails found, output exactly:
  No actionable emails found.

---

### Email Reference
Produce this table for EVERY email scanned (both included and excluded):

| # | From | Subject | Status | Reason |
|---|------|---------|--------|--------|

- **From**: display name only (or part before @ if no display name)
- **Subject**: truncated to 50 chars if needed
- **Status**: ✅ Included or ❌ Excluded
- **Reason**: one concise phrase explaining the decision — e.g. \
"Personal sender, direct ask", "Gmail flagged as Important", "No-reply sender / automated alert", \
"OTP/password reset only", "Transaction receipt, no personal ask", "Promotional, no action required"
- List emails in their original order (Email 1 first, Email N last)
- Never use `|` inside any cell value — replace with `/` if needed

Output the two sections above first, in this exact order:
1. ### Actionable Items  (table or "No actionable emails found.")
2. ### Email Reference   (table covering all emails)

Any additional reasoning or analysis may follow AFTER both sections, separated by a \
horizontal rule (---). Do NOT place any text before the Actionable Items section.
When writing additional notes, use plain language only — do NOT reference internal step \
numbers (Step 1, Step 2, Step 3), pattern numbers (pattern 1, pattern 2), or any other \
internal processing labels. Describe decisions in natural terms (e.g. "automated sender with \
no personal ask" instead of "Step 3 pattern 1").
"""


_COL_WIDTHS: dict[str, str] = {
    # actionable items table
    "#":               "3%",
    "priority":        "8%",
    "action required": "26%",
    "from":            "12%",
    "sender email":    "18%",
    "subject":         "21%",
    "email count":     "8%",
    # email reference table
    "status":          "9%",
    "reason":          "42%",
    # summary statistics table
    "metric":          "30%",
    "value":           "70%",
}


def _reorder_output(text: str) -> str:
    """Ensure output order: Actionable Items → Email Reference → any extra notes.

    Claude occasionally emits preamble or reasoning before the tables despite
    prompt instructions.  This function extracts the two required sections and
    appends any leftover text at the end under an 'Additional Notes' heading.
    """
    actionable_match = re.search(r"(### Actionable Items.*?)(?=### Email Reference|$)", text, re.S)
    reference_match  = re.search(r"(### Email Reference.*?)(?=###|---\s*$|$)", text, re.S)

    actionable = actionable_match.group(1).strip() if actionable_match else "### Actionable Items\nNo actionable emails found."
    reference  = reference_match.group(1).strip()  if reference_match  else "### Email Reference\nNo email reference available."

    # Collect any text that falls outside both sections
    consumed = set()
    if actionable_match:
        consumed.add(actionable_match.group(1))
    if reference_match:
        consumed.add(reference_match.group(1))

    extra = text
    for chunk in consumed:
        extra = extra.replace(chunk, "")
    # Strip horizontal rules and whitespace left behind
    extra = re.sub(r"^[-─━]+\s*$", "", extra, flags=re.M).strip()

    parts = [actionable, reference]
    if extra:
        parts.append("---\n### Additional Notes\n" + extra)

    return "\n\n".join(parts)


def _md_to_html(text: str) -> str:
    """Convert Claude's markdown action-items output to Gmail-compatible HTML."""
    lines = text.split("\n")
    parts: list[str] = []
    table_rows: list[list[str]] = []

    def flush_table() -> str:
        if not table_rows:
            return ""
        out = [
            '<table style="border-collapse:collapse;width:100%;table-layout:fixed;'
            'font-family:Arial,sans-serif;font-size:13px;margin:10px 0 16px">'
        ]
        headers = [c.strip().lower() for c in table_rows[0]] if table_rows else []
        for i, row in enumerate(table_rows):
            tag = "th" if i == 0 else "td"
            row_bg = "background:#e8f0fe;" if i == 0 else (
                "background:#ffffff;" if i % 2 == 1 else "background:#f8f9fa;"
            )
            out.append(f'<tr style="{row_bg}">')
            for j, cell in enumerate(row):
                width_style = ""
                if i == 0:
                    col_key = cell.strip().lower()
                    w = _COL_WIDTHS.get(col_key, "")
                    width_style = f"width:{w};" if w else ""
                cell_style = (
                    f"{width_style}padding:6px 10px;border:1px solid #ddd;"
                    "text-align:left;word-break:break-word;overflow-wrap:break-word;"
                )
                if i == 0:
                    cell_style += "font-weight:bold;color:#1a237e;"
                out.append(f"<{tag} style=\"{cell_style}\">{cell.strip()}</{tag}>")
            out.append("</tr>")
        out.append("</table>")
        table_rows.clear()
        return "\n".join(out)

    def inline(s: str) -> str:
        s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
        s = re.sub(r'\*(.+?)\*',     r'<em>\1</em>',         s)
        return s

    for line in lines:
        stripped = line.strip()

        # ── table row ──────────────────────────────────────────────────────────
        if stripped.startswith("|"):
            cells = [c for c in stripped.split("|") if c != ""]
            # skip separator rows (|---|---|)
            if all(re.match(r'^[\s\-:]+$', c) for c in cells):
                continue
            # If this data row has more cells than the header, merge the extras
            # into the last expected cell (handles stray | inside cell values)
            if table_rows:
                expected = len(table_rows[0])
                if len(cells) > expected:
                    merged = cells[:expected - 1] + [" / ".join(cells[expected - 1:])]
                    cells = merged
            table_rows.append(cells)
            continue

        # flush pending table before any non-table line
        if table_rows:
            parts.append(flush_table())

        # ── headings ───────────────────────────────────────────────────────────
        if stripped.startswith("### "):
            parts.append(
                f'<h3 style="font-family:Arial,sans-serif;font-size:14px;font-weight:bold;'
                f'margin:18px 0 4px;padding-bottom:4px;border-bottom:2px solid #4a90d9;'
                f'color:#1a237e">{inline(stripped[4:])}</h3>'
            )
        elif stripped.startswith("## "):
            parts.append(
                f'<h2 style="font-family:Arial,sans-serif;font-size:16px;margin:20px 0 6px;'
                f'color:#1a237e">{inline(stripped[3:])}</h2>'
            )
        elif stripped == "---":
            parts.append('<hr style="border:none;border-top:1px solid #e0e0e0;margin:14px 0">')
        elif stripped == "":
            parts.append("")
        else:
            parts.append(
                f'<p style="margin:3px 0;font-family:Arial,sans-serif;font-size:13px">'
                f'{inline(stripped)}</p>'
            )

    if table_rows:           # flush any trailing table
        parts.append(flush_table())

    return "\n".join(parts)


def _publish_progress(email: str, title: str, detail: str = "") -> None:
    """Publish an intermediate processing status update to the frontend."""
    publish(email, {
        "type": "agent_complete",
        "processing": True,
        "title": title,
        "body": detail,
    })


async def run_summarizer(email: str, messages_to_process: list[dict]) -> None:
    """
    Background task: summarize the given messages, create a Gmail draft,
    and notify the frontend via SSE.
    """
    user_id = email_to_user_id(email)
    n = len(messages_to_process)
    logger.info("EmailSummarizer | processing %d email(s) for %s", n, email)

    try:
        # 1. Build prompt text for Claude
        _publish_progress(email, f"🔍 Analysing {n} email{'s' if n != 1 else ''}…", "Extracting action items with AI")
        email_text = _format_emails(messages_to_process)

        # 2. Ask Claude to extract action items
        _publish_progress(email, f"🤖 AI processing {n} email{'s' if n != 1 else ''}…", "Claude is identifying action items")
        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            max_retries=0,  # TPM retry loop below owns all waits
            timeout=httpx.Timeout(connect=5.0, read=settings.email_summarizer_read_timeout, write=10.0, pool=5.0),
        )
        # TPM retry: wait 60s if rate-limited, then give up
        response = None
        for _attempt in range(2):
            try:
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=settings.email_summarizer_model_name,
                    max_tokens=settings.email_summarizer_max_tokens,
                    system=_SYSTEM_PROMPT,
                    messages=[
                        {"role": "user", "content": f"Here are my latest unread emails:\n\n{email_text}"}
                    ],
                )
                break
            except anthropic.RateLimitError as exc:
                body_msg = ""
                try:
                    body_msg = exc.body.get("error", {}).get("message", "") if isinstance(exc.body, dict) else ""
                except Exception:
                    pass
                if _attempt == 0 and "tokens per minute" in body_msg.lower():
                    logger.warning("EmailSummarizer | TPM 429 — waiting 60s before retry")
                    _publish_progress(email, "⏳ Rate limit — retrying in 60s…", "Waiting for API quota to reset")
                    await asyncio.sleep(60)
                    continue
                raise
        if response is None:
            raise RuntimeError("EmailSummarizer: no response after TPM retry")
        action_items = _reorder_output(response.content[0].text.strip())

        # Append backend-generated stats section
        stats_block = (
            f"\n\n---\n### Summary Statistics\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Emails scanned | {n} |\n"
            f"| Lookback period | Last {settings.email_lookback_days} days |\n"
            f"| Summariser mode | {settings.email_summarizer_mode} |\n"
            f"| Inclusion rule | {INCLUSION_RULE_SUMMARY} |\n"
            f"| Exclusion rule | {EXCLUSION_RULE_SUMMARY} |\n"
        )
        action_items = action_items + stats_block

        # 3. Create Gmail draft with a unique subject
        _publish_progress(email, "✍️ Saving draft to Gmail…", "Creating action items draft")
        uid = str(uuid.uuid4())[:8].upper()
        today_str = date.today().strftime("%Y-%m-%d")
        subject = f"[ACTION-ITEMS-{today_str}-{uid}]"

        header_html = (
            f'<div style="font-family:Arial,sans-serif;font-size:13px;margin-bottom:16px">'
            f'<h2 style="margin:0 0 4px;color:#1a237e;font-size:16px">'
            f'📋 Email Action Summary — {date.today().strftime("%d %b %Y")}</h2>'
            f'<p style="margin:2px 0;color:#555">'
            f'Scanned: {len(messages_to_process)} email(s) &nbsp;·&nbsp; '
            f'Mode: {settings.email_summarizer_mode}</p>'
            f'<hr style="border:none;border-top:2px solid #4a90d9;margin:10px 0 0">'
            f'</div>'
        )
        draft_body = header_html + _md_to_html(action_items)

        await asyncio.to_thread(
            execute_tool,
            user_id=user_id,
            tool_name="GMAIL_CREATE_EMAIL_DRAFT",
            tool_input={
                "recipient_email": email,
                "subject": subject,
                "body": draft_body,
                "is_html": True,
            },
        )

        # 4. In smart mode, record the processed IDs
        if settings.email_summarizer_mode == "smart":
            ids = [_msg_id(m) for m in messages_to_process if _msg_id(m)]
            if ids:
                mark_ids_processed(email, ids)

        logger.info("EmailSummarizer | completed for %s (draft: %s)", email, subject)
        _notify(
            email,
            "📋 Action items ready",
            action_items,
            draft_subject=subject,
            email_count=len(messages_to_process),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
            mode=settings.email_summarizer_mode,
        )

        # WhatsApp auto-notification intentionally disabled.
        # WA is only sent when the user explicitly clicks "Send test" in the UI
        # or when an agent tool call is made at the user's direct request.

    except Exception as exc:
        logger.exception("EmailSummarizer | failed for %s: %s", email, exc)
        _notify(email, "⚠️ Email summarizer error", str(exc), is_error=True,
                mode=settings.email_summarizer_mode)


def _notify(
    email: str,
    title: str,
    body: str,
    draft_subject: str = "",
    is_error: bool = False,
    email_count: int = 0,
    timestamp: str = "",
    mode: str = "",
) -> None:
    publish(email, {
        "type": "agent_complete",
        "agent": "email_summarizer",
        "title": title,
        "body": body,
        "draft_subject": draft_subject,
        "is_error": is_error,
        "email_count": email_count,
        "timestamp": timestamp,
        "inclusion_rule": INCLUSION_RULE_SUMMARY,
        "exclusion_rule": EXCLUSION_RULE_SUMMARY,
        "mode": mode,
    })


# ── Public entry point ────────────────────────────────────────────────────────

def _two_week_fetch_input() -> dict:
    """Build GMAIL_FETCH_EMAILS tool input scoped to the last 14 days."""
    since = (date.today() - timedelta(days=settings.email_lookback_days)).strftime("%Y/%m/%d")
    return {
        "max_results": settings.email_fetch_limit,
        "label_ids": ["UNREAD"],
        "include_spam_trash": False,
        "query": f"after:{since}",
    }


async def _fetch_and_run(email: str, mode: str) -> None:
    """Fetch emails then summarize. Runs as a background asyncio task so the
    route handler returns immediately after the processing event is published."""
    # Brief delay so the summarizer doesn't compete with the user's first
    # chat message over the shared TPM budget.
    await asyncio.sleep(20)
    user_id = email_to_user_id(email)
    try:
        _publish_progress(email, "📬 Fetching emails…", "Connecting to Gmail inbox")
        # run_in_thread keeps the event loop free so SSE progress events are
        # delivered immediately rather than bunching up after the blocking call
        raw = await asyncio.to_thread(
            execute_tool,
            user_id=user_id,
            tool_name="GMAIL_FETCH_EMAILS",
            tool_input=_two_week_fetch_input(),
        )
        messages = _extract_messages(raw)
        if messages:
            _publish_progress(email, f"📬 Fetched {len(messages)} email{'s' if len(messages) != 1 else ''}…", "Starting analysis")
    except Exception as exc:
        logger.exception("EmailSummarizer | fetch failed for %s: %s", email, exc)
        publish(email, {
            "type": "agent_complete",
            "is_error": True,
            "title": "⚠️ Email summarizer error",
            "body": str(exc),
        })
        return

    if not messages:
        publish(email, {
            "type": "agent_complete",
            "title": "📭 No unread emails",
            "body": "Your inbox is clear for the last 2 weeks.",
        })
        return

    if mode == "smart":
        already_done = get_processed_ids(email)
        messages = [m for m in messages if _msg_id(m) not in already_done]
        if not messages:
            logger.info("EmailSummarizer | all emails already processed for %s", email)
            publish(email, {
                "type": "agent_complete",
                "title": "✅ Already up to date",
                "body": "All recent emails have been scanned.",
            })
            return

    await run_summarizer(email, messages)


def schedule_summarizer(email: str) -> str:
    """
    Evaluate the mode, then immediately publish the processing indicator and
    schedule email fetch + summarization as a background task.

    Returns one of:
      "queued"   — task started
      "disabled" — mode is "off"
    """
    mode = settings.email_summarizer_mode.lower()

    if mode == "off":
        logger.debug("EmailSummarizer | disabled (mode=off)")
        return "disabled"

    if mode in ("always", "smart"):
        # Publish the processing indicator BEFORE any blocking I/O so the
        # frontend animation appears immediately on login.
        publish(email, {
            "type": "agent_complete",
            "processing": True,
            "title": "⏳ Scanning emails…",
            "body": "Scanning your inbox in the background…",
        })
        asyncio.create_task(_fetch_and_run(email, mode))
        return "queued"

    logger.warning("EmailSummarizer | unknown mode %r — treating as off", mode)
    return "disabled"
