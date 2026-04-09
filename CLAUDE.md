# CLAUDE.md

Developer configuration file — provides codebase architecture reference and development guidance for this repository.

> **User-facing documentation** — setup, build, deploy, and API reference: see **[README.md](./README.md)**
>
> Quick links into README:
> - [Prerequisites & installation](./README.md#prerequisites)
> - [Build instructions](./README.md#build)
> - [Deploy instructions](./README.md#deploy)
> - [Environment variables](./README.md#environment-variables)
> - [API reference](./README.md#api-reference)

---

## What This Project Is

A full-stack intelligent assistant that lets users interact with their Gmail, Google Calendar, and Microsoft Outlook via natural language. An LLM API (default: `claude-opus-4-6`) acts as the reasoning engine; Composio handles OAuth (Google and Microsoft) and provides pre-built tool definitions for Gmail, Google Calendar, and Outlook actions. The system auto-detects the email provider at login: `@gmail.com`/`@googlemail.com` → Google Workspace agents; all other domains → Outlook agent.

---

## Project Layout

```
ai-assistant-suite3/
│
├── backend/                          # FastAPI + Python (managed with uv)
│   ├── app/
│   │   ├── main.py                   # FastAPI entry point; injects truststore for macOS SSL
│   │   ├── constants.py              # Application-wide string constants and field names
│   │   ├── config/
│   │   │   └── settings.py           # pydantic-settings — reads backend/.env; all tuneable values
│   │   ├── models/
│   │   │   └── schemas.py            # Pydantic request/response models (incl. trigger schemas)
│   │   ├── core/
│   │   │   ├── agent.py              # Streaming agentic loop (SSE); four-agent system prompts
│   │   │   ├── composio_client.py    # Composio v1: tool fetch/execute + trigger enable/disable + provider-aware profile fetchers
│   │   │   ├── email_summarizer.py   # Login-triggered email action-item summariser
│   │   │   ├── history_store.py      # TinyDB chat history persistence (data/history_store.json)
│   │   │   ├── notifier.py           # Twilio WhatsApp: send_whatsapp() + format_trigger_message()
│   │   │   ├── profile_store.py      # TinyDB persistent profile cache with provider segregation (data/profile_cache.json)
│   │   │   ├── session_store.py      # In-memory session store keyed by email; restores history on create
│   │   │   ├── token_store.py        # TinyDB session token store (data/token_store.json)
│   │   │   └── trigger_store.py      # In-memory per-user asyncio.Queue fanout for SSE delivery
│   │   └── api/
│   │       └── routes/
│   │           ├── auth.py           # POST /api/auth/initiate, GET /api/auth/status/{email}, POST /api/auth/logout
│   │           ├── chat.py           # POST /api/chat/message → SSE stream (token-protected)
│   │           ├── notifications.py  # GET/POST /api/notifications/whatsapp — settings + test (token-protected)
│   │           ├── settings.py       # GET/POST /api/settings — backend env var management
│   │           └── triggers.py       # Trigger management + Composio webhook receiver + SSE stream (token-protected)
│   └── pyproject.toml
│
├── frontend/                         # Next.js 15 (App Router, TypeScript, Tailwind CSS)
│   ├── app/
│   │   ├── layout.tsx                # Root layout
│   │   ├── page.tsx                  # Main page: auth gate + chat layout + resizable sidebar + TriggerToast
│   │   └── auth/
│   │       └── callback/
│   │           └── page.tsx          # Google/Microsoft OAuth return handler
│   ├── components/
│   │   ├── Auth/
│   │   │   └── ConnectButton.tsx     # Email input + Google/Microsoft connect form (auto-detects provider)
│   │   ├── Chat/
│   │   │   ├── ChatWindow.tsx        # Scrollable message list + personalised empty state
│   │   │   ├── MessageBubble.tsx     # Renders user/assistant bubbles + markdown tables
│   │   │   ├── MessageInput.tsx      # Textarea + voice input + agent selector + send button
│   │   │   └── SuggestionsPane.tsx   # Left sidebar: per-agent collapsible quick actions (CRUD)
│   │   ├── ui/
│   │   │   ├── icons.tsx             # Shared SVG icon components (Spinner, BellIcon, SendIcon, etc.)
│   │   │   └── MarkdownContent.tsx   # Shared markdown renderer incl. EditableBlock (editable code fences)
│   │   ├── Notifications/
│   │   │   ├── NotificationDrawer.tsx  # Bell icon + drawer; processing progress bar + timer
│   │   │   ├── NotificationListener.tsx # EventSource consumer; maps SSE events to state
│   │   │   ├── TriggerToast.tsx      # Slide-in toast for trigger events only (not summariser)
│   │   │   └── WhatsAppSettings.tsx  # WA settings dropdown (phone, enable toggle, send test)
│   │   └── Settings/
│   │       └── SettingsPanel.tsx     # Slide-in panel: view + update backend .env vars from UI
│   └── lib/
│       ├── agents.ts                 # AGENT_META map + AgentColors tokens (workspace/gmail/calendar/outlook)
│       ├── api.ts                    # All backend fetch calls + SSE async generator + token management
│       ├── constants.ts              # Frontend magic values (timeouts, limits, storage keys, URLs)
│       ├── icons.ts                  # autoIcon() — derives emoji from trigger/action name via regex
│       ├── styles.ts                 # UI namespace: shared Tailwind class strings (btn, input, badge, card, alert)
│       └── types.ts                  # Shared TypeScript types (Message, SSEEvent, AgentType)
│
├── res.sh                            # Full rebuild (9 steps) — replaces restart.sh
├── bk.sh                             # Backend-only restart (Python edits, no dep changes)
├── bk2.sh                            # Backend restart + uv sync (pyproject.toml changed)
├── fn.sh                             # Frontend-only rebuild (TSX/TS/CSS edits, no new packages)
├── fn2.sh                            # Frontend rebuild + npm install (new Node packages)
└── package.json                      # Root: concurrently dev script
```

---

## Setup

> Full prerequisites, build steps, and deploy instructions are in **[README.md → Build](./README.md#build)** and **[README.md → Deploy](./README.md#deploy)**.

### Quick reference (dev)

```bash
cp backend/.env.example backend/.env   # fill in API keys (see README → Environment Variables)
npm run install:all                    # Node packages
cd backend && uv sync && cd ..         # Python packages
npm run dev                            # frontend :3000  backend :8000
```

`backend/.env` required keys: `ANTHROPIC_API_KEY`, `COMPOSIO_API_KEY`, `GMAIL_AUTH_CONFIG_ID`, `CALENDAR_AUTH_CONFIG_ID`.
Optional: `OUTLOOK_AUTH_CONFIG_ID` (for Microsoft Outlook users).
Optional: `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` + `TWILIO_WHATSAPP_FROM` (WhatsApp notifications — see [README → WhatsApp Notifications](./README.md#whatsapp-notifications)).

### Quick reference (production rebuild)

```bash
bash res.sh          # full rebuild (both services)
bash bk.sh           # backend only — Python edits, .env changes
bash bk2.sh          # backend + uv sync — pyproject.toml changed
bash fn.sh           # frontend only — TSX/TS/CSS edits
bash fn2.sh          # frontend + npm install — new Node packages
```

`res.sh` — 9 steps: kills ports → **parallel** `uv sync` + `npm install` → localStorage key bump → **smart** `.next` wipe (only if tsconfig/tailwind/package.json changed) → `npm run build` → start backend → start frontend → **polling** health checks. Exits non-zero on failure. Logs: `logs/app.log`.

---

## Key Architecture

### Auth & session flow

1. User enters email address (Gmail or any other) → `POST /api/auth/initiate` with `agent_type: "gmail"` or `"outlook"` based on domain
2. Backend derives a Composio `user_id` from the email via `re.sub(r'[^a-zA-Z0-9_-]', '_', email.lower())`
3. Checks existing Composio connections → if active, returns `{connected: true, session_token: "<token>"}` and chat opens
4. Otherwise returns `{auth_url: "..."}` → frontend redirects user to Google OAuth
5. After consent, user lands on `/auth/callback` → reads `?email=` param (or `localStorage.pending_email`) → stores `user_email` in localStorage → redirects to `/`
6. Frontend calls `POST /api/auth/initiate` again on landing → receives `session_token`, stored in `localStorage.session_token`
7. All protected API calls include `session_token` in the request body; the SSE stream passes it as `?token=` query param
8. Sign-out calls `POST /api/auth/logout` → **full flush**: token revoked in TinyDB, chat history cleared (all 3 agents), profile cache cleared, in-memory session evicted, **tool schema cache evicted** (`evict_tools_cache(user_id)`) → `session_token` cleared from localStorage. Next login fetches fresh Google Contacts, profile data, and tool schemas.

Sessions are **email-keyed** in-memory. Session tokens and chat history persist across backend restarts (TinyDB).

### Four subagents (`backend/app/core/agent.py`)

`agent_type: "gmail" | "calendar" | "workspace" | "outlook"` is sent with every chat message and controls three things:

| What | Gmail | Calendar | Workspace | Outlook |
|---|---|---|---|---|
| Provider | Google | Google | Google | Microsoft |
| Composio toolkit | `["gmail", "googlecontacts"]` | 10 calendar tools + contacts | 11 Gmail + 10 calendar (21 total) | 31 curated Outlook tools |
| System prompt | `GMAIL_SYSTEM_PROMPT` | `CALENDAR_SYSTEM_PROMPT` | `WORKSPACE_SYSTEM_PROMPT` | `OUTLOOK_SYSTEM_PROMPT` |
| History | `session.gmail_messages` | `session.calendar_messages` | `session.workspace_messages` | `session.outlook_messages` |
| Available to | Gmail users | Gmail users | Gmail users | Non-Gmail users |

Each agent has its own isolated history stored in the `Session` dataclass; clearing one does not affect the other.

The **workspace** agent is a superset — it receives 11 curated Gmail tools (`_GMAIL_WORKSPACE_TOOLS`) + 10 core Calendar tools (`_CALENDAR_ALL_TOOLS`) = 21 tools total. Trimmed from the original 60 tools (~65% reduction) to keep input token cost manageable. Use it for cross-domain tasks (e.g. "email everyone on tomorrow's meeting").

**Tool budget rationale**: Anthropic TPM limits are per-model per-org. Each tool schema costs ~1,500 input tokens; 60 tools × 1,500 = ~90K tokens per API call iteration. Trimming to 21 tools reduces this to ~32K. The workspace agent runs on `claude-opus-4-6`; the email summariser runs on `claude-haiku-4-5-20251001` — separate TPM pools, no cross-competition.

**Agent loop**:

```
User message + agent_type  ("gmail" | "calendar" | "workspace" | "outlook")
  → fetch Composio toolkit for agent_type
  → inject send_whatsapp_notification custom tool
  → LLM stream  (model=claude-opus-4-6, thinking={type:"adaptive"})
  → if stop_reason == "tool_use":
      → if send_whatsapp_notification: handle locally via notifier.py
      → otherwise: execute via composio_client.execute_tool()
          → Calendar events: _strip_calendar_event() keeps only essential fields;
            cap at calendar_tool_result_chars (50 K default)
          → Gmail/other: truncate to max_tool_result_chars (8 K); email bodies capped at 500 chars
      → append tool_results as user turn
      → loop
  → trim history to last 10 turns before each API call
  → save history to TinyDB (history_store.save_history) before yielding "done"
  → SSE events yielded:
      {"type": "text",       "content": "<delta>"}
      {"type": "tool_start", "name": "GMAIL_FETCH_EMAILS", "display": "..."}
      {"type": "tool_end",   "name": "GMAIL_FETCH_EMAILS", "success": true}
      {"type": "done"}
      {"type": "error",      "message": "..."}
```

Thinking blocks are **excluded** from serialised history (prevents context bloat without losing capability).

### Trigger notification loop (`trigger_store.py` + `triggers.py`)

Runs independently of the agent loop — no LLM involved:

```
POST /api/triggers/webhook  (Composio → FastAPI)
  → resolve email from metadata.client_unique_user_id
  → trigger_store.publish(email, {type, trigger_name, label, icon, payload})
  → asyncio.Queue.put_nowait() for every open SSE connection for that user
  → if session.wa_notifications_enabled and session.whatsapp_number:
      → asyncio.create_task(send_whatsapp(...))  ← fire-and-forget

GET /api/triggers/stream/{email}  (frontend EventSource)
  → sse_generator() yields queue items as "data: {...}\n\n"
  → keepalive ": keepalive\n\n" every 20 s
  → TriggerToast.tsx renders slide-in toast for trigger events only
  → agent_complete (email summariser) goes to bell drawer + sidebar strip only — no toast pop-up
```

### Session token authentication (`core/token_store.py`)

- `create_token(email)` → `secrets.token_urlsafe(32)` — upserts one active token per user in TinyDB `data/token_store.json`. Reconnecting invalidates the previous token.
- `validate_token(email, token)` → `secrets.compare_digest` — timing-safe comparison. Called via `_require_token(email, token)` helper in each route file (raises HTTP 401 on mismatch).
- `revoke_token(email)` → removes record. Called by `POST /api/auth/logout`.
- The SSE stream endpoint (`GET /api/triggers/stream/{email}`) cannot use request body, so the token is passed as `?token=` query parameter.

### Chat history persistence (`core/history_store.py`)

- TinyDB at `data/history_store.json`; keyed by `"email:agent_type"`.
- `save_history(email, agent_type, messages)` — called in `stream_agent_response` right before `yield _sse({"type": "done"})`.
- `load_history(email, agent_type)` — called in `SessionStore.get_or_create()` for all three agents, so history is immediately available after a restart.
- `clear_history(email, agent_type=None)` — called from `POST /api/chat/clear`; clears one or all agents.

### WhatsApp notification helper (`core/notifier.py`)

- `normalise_e164(phone)` — strips whitespace/dashes/parens, validates `+` prefix + 7–15 digits; raises `ValueError` with a user-friendly message if invalid.
- `send_whatsapp(to, message)` — returns `(bool, str)` tuple (success, error message). Validates E.164 first; truncates message to 1500 chars to stay within Twilio's limit; parses Twilio HTTP error body for `code`, `message`, and `more_info` to surface actionable errors. No-op (returns `False, msg`) if Twilio credentials are not configured.
- `format_trigger_message(event)` — converts the trigger event dict into a readable WhatsApp message string (icon + label + key payload fields).
- WhatsApp settings (phone number + enabled flag) are stored per-user in `Session.whatsapp_number` / `Session.wa_notifications_enabled` (in-memory, cleared on restart).
- The `send_whatsapp_notification` agent tool always targets the user's **own** registered number — agents are instructed to compose and send immediately without asking for recipient confirmation.
- All callers (`agent.py`, `email_summarizer.py`, `triggers.py`, `notifications.py`) unpack the `(bool, str)` return and surface errors via SSE `agent_complete` event or agent tool result JSON.

### API error handling & retries (`core/agent.py`)

- `_anthropic_client` configured with `max_retries=0` and `httpx.Timeout(connect=5s, read=15s, write=10s, pool=5s)`. SDK retries are disabled because they fire within the same 60s TPM window and are useless for rate-limit recovery.
- **TPM retry loop**: on a 429 where the message body contains `"tokens per minute"`, the loop waits 60s (retry 1) then 90s (retry 2) before giving up. The user sees an SSE progress message during each wait.
- **Transient retry**: on 500/529/connection errors, silent backoff 2s → 4s → 6s (3 attempts).
- **Tool fetch retry**: `_get_tools_cached()` retries Composio 500 errors up to 3 times with 2s/4s backoff.
- `_format_api_error(exc)` maps Anthropic SDK exceptions to structured `{error_code, message}` dicts:
  - `APIStatusError` → HTTP status code (e.g. `"429"`, `"529"`) + label from `_ANTHROPIC_ERROR_LABELS`
  - `APITimeoutError` → `"TIMEOUT"`
  - `APIConnectionError` → `"CONNECTION_ERROR"`
- The frontend displays `error_code` as a bracketed badge before the error message (e.g. `[429] Rate Limited…`).
- **Token usage logging**: `[PRE-CALL]` is printed to stdout (captured in `app.log`) before every API call showing estimated chars/tokens; `[TOKEN USAGE]` is printed after every successful call showing actual Anthropic-reported `input_tokens` and `output_tokens`.
  ```bash
  grep 'TOKEN USAGE\|PRE-CALL' logs/app.log | tail -20
  ```

### Calendar event fetch (`core/composio_client.py` + `core/agent.py`)

- `_TOOL_ARG_DEFAULTS` in `composio_client.py` injects `maxResults=2000` into every `GOOGLECALENDAR_EVENTS_LIST` call regardless of what the LLM passes — prevents Composio's default of 5 from silently capping results.
- `_strip_calendar_event(event)` in `agent.py` retains only `_CALENDAR_EVENT_KEEP_FIELDS` (id, summary, description, start, end, status, location, attendees, organizer, recurrence) and trims per-attendee data to `_CALENDAR_ATTENDEE_KEEP_FIELDS`. Descriptions capped at 200 chars.
- `_MAX_CALENDAR_TOOL_RESULT_CHARS = settings.calendar_tool_result_chars` (default 50 000) — separate higher cap for calendar lists vs the 8 K general cap.
- `_truncate_tool_result()` detects calendar responses by checking for `items`/`events`/`data` list key, strips fields first, then applies the calendar cap. If still over, returns as many complete events as fit (no mid-JSON truncation).

### Email Summariser (`core/email_summarizer.py`)

- **Dedicated model** — runs on `settings.email_summarizer_model_name` (default: `claude-haiku-4-5-20251001`). Using a different model from the chat agent (`claude-opus-4-6`) gives each a separate TPM pool — they cannot starve each other. Override via `EMAIL_SUMMARIZER_MODEL_NAME` in `.env`.
- **Startup delay** — `_fetch_and_run` sleeps 20s after being triggered so the summariser doesn't compete with the user's first chat message over the shared TPM budget.
- **TPM retry** — on a 429 with `"tokens per minute"` in the body, waits 60s and retries once; publishes a progress SSE during the wait. `max_retries=0` on the Anthropic client (SDK retries are useless within the same window).
- **Output tables** — two sections rendered as HTML via `_md_to_html()`:
  - *Actionable Items*: `#` · Priority · Action Required · From · Sender Email · Subject
  - *Excluded Emails*: `#` · From · Subject · Reason Excluded (Gmail Category removed)
- **Deduplication** — rows describing the same real-world task are merged; highest-priority row is kept.
- **HTML rendering** — `_md_to_html()` is called before the draft tool (`GMAIL_CREATE_EMAIL_DRAFT` or `OUTLOOK_CREATE_DRAFT`); `is_html: True` passed to Composio for both Gmail and Outlook so the provider renders tables correctly. `_COL_WIDTHS` dict assigns `%`-based widths per column header; `table-layout:fixed` + `word-break:break-word` enforce alignment.
- **Pipe safety** — Claude is instructed to replace `|` in cell values with `/`; parser merges over-split rows back to the expected column count.
- **Output ordering** — `_reorder_output(text)` post-processes Claude's response to enforce section order: `### Actionable Items` → `### Email Reference` → `### Additional Notes`. Any preamble/reasoning is appended last. Additional notes are written in plain language — internal step/pattern numbers are explicitly suppressed in the prompt.
- **Email Count column** — Actionable Items table now includes an `Email Count` column; deduplicated rows show the count of merged source emails.
- **Email Reference table** — replaces "Excluded Emails"; covers every scanned email (both ✅ Included and ❌ Excluded) with a Status and Reason column.
- **Summary Statistics** — backend-appended table after Claude's output: emails scanned, lookback period, mode, provider, inclusion rule, exclusion rule.
- **Provider-aware draft link** — `_notify()` includes `provider: "Gmail" | "Outlook"` in the SSE event. Frontend components (`NotificationDrawer`, `TriggerToast`) use this to render the correct link: Gmail → `https://mail.google.com/mail/u/0/#search/{subject}` ("Open in Gmail →"); Outlook → `https://outlook.live.com/mail/0/drafts` ("Open in Outlook →"). Constants: `GMAIL_SEARCH_BASE_URL`, `OUTLOOK_DRAFTS_URL` in `frontend/lib/constants.ts`.
- **WA auto-send removed** — `send_whatsapp` is no longer called automatically from `email_summarizer.py` or `triggers.py`. WA is only sent via the "Send test" UI button or an explicit agent tool call at the user's request.
- **WA summary** — sends up to 10 action rows (pipe-delimited lines), hard-capped at 1500 chars.
- **Schedule & Meet (Stage 1)** — workspace/calendar agent always responds with a fillable code-block template (`Title / Date / Duration / Attendees / Agenda`) so the "Use this ↗" EditableBlock appears immediately. Default meeting duration is **30 minutes** across all agent prompts and quick actions.
- **Rescheduling confirmation (Calendar + Workspace agents)** — both system prompts instruct the agent to always seek explicit user approval before rescheduling any conflicting event. The agent presents the conflicting event details and the proposed new time, then waits for user confirmation before calling any update/patch/delete tool. Automatic rescheduling without user approval is explicitly prohibited.
- **Workspace quick action w7** — "Share Action Items - WhatsApp (via Twilio)": the prompt is intentionally written in plain first-person user language to avoid false-positive prompt-injection detection by the model. It instructs the agent to find the latest Gmail draft with `ACTION-ITEMS` in the subject, display the draft subject and action items, then ask (1) which items to share and (2) who to send them to — resolving the recipient's WhatsApp/mobile number from Google Contacts before sending via WhatsApp. Technical tool names, raw query strings, and any "silently resolve" directives are kept out of the prompt text to prevent the model from flagging it as injected content.

### Frontend style tokens (`frontend/lib/styles.ts` + `frontend/lib/agents.ts`)

`lib/styles.ts` — `UI` namespace is the single source of truth for shared Tailwind class strings:
- `UI.btn.primary/secondary/iconAccent/iconDanger/iconClose`
- `UI.input.base/textarea/settings`
- `UI.badge.suggestion/statusRunning/statusDone/statusError/savedPill`
- `UI.card.form/danger`
- `UI.alert.error/success`

`lib/agents.ts` — `AGENT_META[type].colors` (`AgentColors` interface with 11 token fields) drives all per-agent colour in `MessageInput`, `MessageBubble`, and `SuggestionsPane`. No local `AGENT_CONFIG`, `AGENT_BADGE_CLS`, or `SECTION_META` constants remain in component files.

### Notification state split (`frontend/app/page.tsx`)

Two separate state variables track notifications:
- `pendingToast` — only set for `type === "trigger"` events; feeds `TriggerToast` slide-in
- `sidebarNotification` — set for all events (triggers + agent_complete); feeds the `SuggestionsPane` status strip

This means the email summariser processing/complete state is visible in the sidebar and bell drawer without triggering a separate pop-up toast.

### Frontend SSE (`frontend/lib/api.ts`)

Uses `fetch` + `ReadableStream` (not `EventSource`) because the chat endpoint is a POST. `streamMessage()` is an async generator yielding typed `SSEEvent` objects. Session token helpers: `getStoredToken()` / `storeSessionToken()` / `clearSessionToken()` read/write `localStorage.session_token`. `triggerStreamUrl(email)` builds the authenticated EventSource URL with `?token=`.

### Markdown rendering (`frontend/components/ui/MarkdownContent.tsx`)

Shared zero-dependency renderer used by `MessageBubble.tsx` (and any other consumer):
- Code fences → `EditableBlock` (when `onEditableBlock` prop is provided): an editable `<textarea>` with a "Use this ↗" button that pastes the edited content into the message input. Falls back to `<pre><code>` if no callback.
- `|`-delimited blocks → full `<table>` with styled header row and alternating row colours
- `**bold**`, `*italic*`, `` `code` `` → inline `<strong>`, `<em>`, `<code>`
- Bullet lines (`- ` / `* ` / `• `) → `<ul><li>`
- Numbered lines (`1. ` / `  3. ` etc.) → `<ol start={N}>` — reads the actual first number so lists interrupted by headings/text resume at the correct sequence; indented numbered items also matched
- Heading lines (`# ` / `## `) → `<h3>` / `<h4>`

`MessageBubble.tsx` passes `onEditableBlock` which routes the accepted text back through `onSuggestion(text, agentType)` so it lands in the message input pre-filled.

### Persistent profile cache (`core/profile_store.py`)

TinyDB store at `backend/data/profile_cache.json` with provider segregation (`"gmail"` or `"outlook"`). Survives backend restarts — on the first request after a restart, sessions auto-restore cached display name, timezone, locale, calendars, and frequent contacts without re-fetching from provider APIs.

- `save_profile(email, display_name, profile, provider)` — called in `preload_session`, `get_greeting`, and `stream_agent_response` (fallback)
- `load_profile(email)` → `(display_name, profile, fetched_at, provider)` — called in `SessionStore.get_or_create()`

Profile data is fetched from provider-specific APIs:
- **Gmail**: `GMAIL_GET_PROFILE`, `GOOGLECALENDAR_SETTINGS_LIST`, `GOOGLECALENDAR_LIST_CALENDARS`, `GOOGLECONTACTS_LIST_CONTACTS`, `GOOGLECALENDAR_GET_CURRENT_DATE_TIME`
- **Outlook**: `OUTLOOK_GET_MAILBOX_SETTINGS` (fetched first for timezone; Windows TZ → IANA conversion), `OUTLOOK_GET_PROFILE`, `OUTLOOK_LIST_CALENDARS`, `OUTLOOK_LIST_USER_CONTACTS`, then local `current_datetime` computation via `zoneinfo`

### Frequent contacts in profile block

Frequent contacts are fetched from the appropriate provider: `GOOGLECONTACTS_LIST_CONTACTS` for Gmail users, `OUTLOOK_LIST_USER_CONTACTS` for Outlook users (includes phone numbers). `_build_profile_block()` renders these into the system prompt under a "Frequent Contacts" section with provider-aware instructions — Gmail agents check contacts before calling `GOOGLECONTACTS_*`; Outlook agents check before calling `OUTLOOK_LIST_USER_CONTACTS`.

### localStorage version keys

Quick-action defaults are cached under `quick_actions_gmail_vN` / `quick_actions_calendar_vN`. `res.sh` Step 4 hashes the `{ id:` entries in `SuggestionsPane.tsx` and auto-increments the version number when the hash differs, forcing the browser to reload fresh defaults. Hash stored in `.defaults_hash` at project root.

**Merge behaviour (label/text updates without ID change):** On load, `SuggestionsPane` maps stored suggestions against the current defaults by ID. Any stored entry whose ID matches a default is refreshed with the latest `label` and `text` from code — so renaming a suggestion or updating its prompt is always picked up on next page load without a version bump or ID change. User-added custom suggestions (IDs not in defaults) are never overwritten.

`sidebar_width` — drag-resized sidebar width (integer px, range 180–520). Set by the drag handle in `page.tsx`; TriggerToast position follows the same value dynamically.

---

## API Reference (current)

### Auth & Chat

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/initiate` | Start Google/Microsoft OAuth or confirm existing connection. Returns `session_token` when connected. |
| GET  | `/api/auth/status/{email}` | Poll connection status (Gmail+Calendar or Outlook). Returns `session_token` when connected. |
| POST | `/api/auth/logout` | Revoke token `{email}` |
| POST | `/api/chat/message` | Send `{email, message, agent_type, session_token}`, returns SSE stream |
| POST | `/api/chat/clear` | Clear history `{email, agent_type?, session_token}` |
| GET  | `/health` | Liveness check |

### Triggers

| Method | Path | Description |
|---|---|---|
| GET  | `/api/triggers/available` | List all supported trigger types (Gmail + Calendar) |
| GET  | `/api/triggers/active/{email}` | List triggers active for this user with subscription IDs |
| POST | `/api/triggers/subscribe` | Enable a trigger `{email, trigger_name, config?, session_token}` |
| POST | `/api/triggers/unsubscribe` | Disable a trigger `{email, trigger_subscription_id, session_token}` |
| POST | `/api/triggers/webhook` | Composio calls this when a trigger fires (set in Composio dashboard) |
| GET  | `/api/triggers/stream/{email}` | Long-lived SSE `?token=<session_token>` — frontend connects here to receive toast events |

### WhatsApp Notifications

| Method | Path | Description |
|---|---|---|
| GET  | `/api/notifications/whatsapp/{email}` | Fetch saved phone number + enabled flag |
| POST | `/api/notifications/whatsapp` | Save `{email, whatsapp_number, enabled, session_token}` |
| POST | `/api/notifications/whatsapp/test` | Send a test message `{email, whatsapp_number, session_token}` |

### Settings

| Method | Path | Description |
|---|---|---|
| GET  | `/api/settings` | List all backend env vars (sensitive values masked) |
| POST | `/api/settings` | Update env vars `{updates: {key: value}}` |

---

## Composio Integration Notes (v1.0.0-rc2)

### Tools (actions the agent calls)

- **Client init**: `Composio(provider=AnthropicProvider(), api_key=...)`
- **Tool fetch**: `composio.tools.get(user_id=..., toolkits=["gmail", "googlecontacts"])` / calendar uses explicit `tools=[...]` list (all 40 tools) + contacts merged in
- **Tool execute**: `composio.tools.execute(slug=name, arguments=input, user_id=..., dangerously_skip_version_check=True)`
  - `dangerously_skip_version_check=True` is required — without it `ToolVersionRequiredError` is raised
  - Returns a plain `dict`; check `result.get("error")` for failures
- **Connection check**: `composio.connected_accounts.list(user_ids=[user_id], toolkit_slugs=["gmail","googlecalendar"], statuses=["ACTIVE"])`
- **AUTH_CONFIG_ID**: create in Composio dashboard → Integrations → Google. Must include both Gmail **and** Google Calendar API scopes. Users who authenticated before Calendar scopes were added must re-connect.

### Triggers (Composio calls your backend)

Triggers are event-driven: Composio polls or watches Google services and POSTs to your webhook. They do **not** go through the agent tool loop.

**Gmail triggers** (`GMAIL_TRIGGERS` in `composio_client.py`):

| Slug | Label |
|---|---|
| `GMAIL_NEW_EMAIL_EVENT` | 📨 New Email Received |
| `GMAIL_MESSAGE_SENT` | 📤 Email Sent |

**Calendar triggers** (`CALENDAR_TRIGGERS` in `composio_client.py`):

| Slug | Label |
|---|---|
| `GOOGLECALENDAR_EVENT_CREATED` | ✅ Event Created |
| `GOOGLECALENDAR_EVENT_UPDATED` | ✏️ Event Updated |
| `GOOGLECALENDAR_EVENT_CANCELLED` | ❌ Event Cancelled |
| `GOOGLECALENDAR_ATTENDEE_RESPONSE_CHANGED` | 🔔 Attendee Response |
| `GOOGLECALENDAR_EVENT_STARTING_SOON` | ⏰ Starting Soon |
| `GOOGLECALENDAR_CALENDAR_EVENT_SYNC` | 🔄 Event Sync |

**Trigger management** (`composio_client.py`):
- `enable_trigger(user_id, trigger_name, config?)` → `composio.triggers.enable(...)`
- `disable_trigger(subscription_id)` → `composio.triggers.disable(...)`
- `list_active_triggers(user_id)` → `composio.triggers.list(connected_account_id=...)`
- `get_connected_account_id(user_id)` — resolves the active Google account ID needed for trigger calls

**One-time setup**:
1. Composio dashboard → Settings → Webhooks: set URL to `https://<your-domain>/api/triggers/webhook`
2. For local dev: `ngrok http 8000` and use the ngrok URL
3. Subscribe users via `POST /api/triggers/subscribe`

---

## SSL Note (macOS / Python 3.13 Homebrew)

`httpx` (used by Composio SDK) cannot verify TLS with the system Python 3.13 cert store on macOS. Fix already applied in `main.py`:

```python
import truststore
truststore.inject_into_ssl()
```

`truststore` is listed in `pyproject.toml`. Do not remove this call.
