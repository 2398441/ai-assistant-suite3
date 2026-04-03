# AI Assistant Suite

> A full-stack intelligent assistant for Gmail, Google Calendar, and Microsoft Outlook — interact with your inbox and schedule using natural language. Supports both Google Workspace and Microsoft 365 users.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Build](#build)
- [Deploy](#deploy)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Trigger System](#trigger-system)
- [WhatsApp Notifications](#whatsapp-notifications)
- [Development](#development)
- [Known Platform Notes](#known-platform-notes)
- [Security & Known Limitations](#security--known-limitations)

---

## Overview

AI Assistant Suite connects to a user's Google account (Gmail + Google Calendar) or Microsoft 365 account (Outlook) via OAuth and exposes a natural-language chat interface. Users can compose emails, check their calendar, manage drafts, schedule meetings, manage contacts, and receive real-time notifications — all through conversational messages.

The system detects the email provider at login: `@gmail.com` / `@googlemail.com` routes to Google Workspace agents (Gmail, Calendar, Workspace); all other domains route to the Outlook agent with full email, calendar, and contacts capabilities.

The backend runs an agentic loop that routes user intent to the correct set of provider tools, streams responses token-by-token to the browser, and independently delivers event-driven notifications (new emails, calendar updates) as slide-in toasts via Server-Sent Events.

---

## Features

| Feature | Description |
|---|---|
| **Natural Language Gmail** | Compose, read, search, reply, and manage drafts via chat |
| **Natural Language Calendar** | Create events, check availability, list upcoming meetings |
| **Natural Language Outlook** | Full email, calendar, and contacts management for Microsoft 365 users — including meeting scheduling with Teams link generation |
| **Multi-provider Auth** | Email domain auto-detection: Gmail users get Gmail/Calendar/Workspace agents; all other domains get the Outlook agent |
| **Agent Routing** | Dedicated Gmail, Calendar, Workspace, and Outlook agents with isolated conversation histories |
| **Streaming Responses** | Token-by-token SSE streaming for real-time chat feel |
| **Quick Actions** | Configurable sidebar of one-click prompts per agent (persisted to localStorage) |
| **Voice Input** | Browser-native Web Speech API for hands-free message entry |
| **Real-time Notifications** | Event-driven toasts for incoming emails, sent messages, and calendar changes |
| **Processing Indicators** | Live spinner, shimmer, indeterminate progress bar, and elapsed timer while the email summariser runs |
| **Trigger Management** | Subscribe / unsubscribe to Gmail and Calendar webhook triggers from the UI |
| **Email Action Summary** | On login, unread emails are scanned (Gmail or Outlook); deduped action items (with Sender Email + Email Count columns), full Email Reference table, and Summary Statistics saved as an HTML draft in the user's provider |
| **WhatsApp Notifications** | Sent only on explicit "Send test" button click or direct agent request — never auto-fired on login or trigger events; E.164 validation, Twilio error surfacing, 1500-char cap |
| **Markdown Rendering** | Tables, code blocks, bold, italic, lists, and headings rendered in chat |
| **Editable Pre-fill Blocks** | Code fences in assistant replies become editable text areas; click "Use this ↗" to send pre-filled content |
| **Resizable Sidebar** | Drag the handle between sidebar and chat to resize; width persisted in localStorage |
| **Personalised Greeting** | First name resolved from Google profile or Outlook profile, persisted across restarts, shown in header and empty state |
| **Persistent Profile Cache** | User timezone, calendars, and frequent contacts cached in TinyDB with provider segregation (Gmail vs Outlook) — survives backend restarts |
| **Session Token Auth** | Cryptographically random session tokens issued on connect; all protected routes validated — multi-user isolation |
| **Chat History Persistence** | Conversation history saved to TinyDB per user per agent; survives backend restarts |
| **Full Logout Flush** | Sign-out revokes the session token, clears chat history and profile cache from TinyDB, evicts the in-memory session, and clears the in-memory tool schema cache — next login starts completely fresh |
| **Calendar Event Completeness** | `GOOGLECALENDAR_EVENTS_LIST` always requests up to 2000 events; results are field-stripped and held under a 50 K character cap so the LLM sees all events, not just the first 5 |
| **API Error Codes in UI** | Structured Anthropic error codes (e.g. `429`, `TIMEOUT`, `529`) surfaced as a badge in the chat bubble; custom TPM retry loop (60s + 90s waits) and transient error backoff — SDK retries disabled to avoid wasting quota within the same window |
| **Settings Panel** | In-app UI to view and update backend environment variables without editing `.env` directly |

---

## Tech Stack

### Frontend
| Layer | Technology |
|---|---|
| Framework | Next.js 15 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS (custom `shimmer` + `indeterminate` keyframes) |
| Chat streaming | `fetch` + `ReadableStream` (POST-based SSE) |
| Notifications | Browser `EventSource` (GET-based SSE) |

### Backend
| Layer | Technology |
|---|---|
| Framework | FastAPI (Python) |
| Package manager | `uv` |
| AI model | Anthropic API — `claude-opus-4-6` (configurable) |
| Suggestions model | `claude-haiku-4-5-20251001` (configurable) |
| Google integration | Composio v1 (OAuth + pre-built Gmail / Calendar tools) |
| Outlook integration | Composio v1 (OAuth + pre-built Outlook tools — 31 curated from 200+) |
| WhatsApp | Twilio WhatsApp API (direct `httpx` calls) |
| Settings | `pydantic-settings` — all tuneable values in `.env` |
| SSL (macOS) | `truststore` |

---

## Prerequisites

### Runtime Tools

| Tool | Version | Purpose |
|---|---|---|
| Node.js | ≥ 18 | Next.js frontend runtime |
| npm | ≥ 9 | Frontend package management |
| Python | ≥ 3.11 | FastAPI backend runtime |
| `uv` | latest | Python package manager |
| ngrok | any | Webhook tunnel for local dev |

```bash
# macOS (Homebrew) — install all at once
brew install node python@3.11 ngrok

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### External Accounts & API Keys

| Service | Where to obtain | Required |
|---|---|---|
| Anthropic API key | [console.anthropic.com](https://console.anthropic.com) → API Keys | ✅ |
| Composio API key | [composio.dev](https://composio.dev) → Settings → API Keys | ✅ |
| Composio Auth Config IDs (Google) | Composio dashboard → Integrations → Google | ✅ |
| Composio Auth Config ID (Outlook) | Composio dashboard → Integrations → Outlook | Optional |
| Twilio credentials | [console.twilio.com](https://console.twilio.com) | Optional |

#### Creating the Composio Auth Configs

**Google (Gmail + Calendar):**

1. Log into [composio.dev](https://composio.dev) → **Integrations → Google**
2. Create a new integration — enable both **Gmail** and **Google Calendar** API scopes
3. Copy the generated **Auth Config ID** — set as both `GMAIL_AUTH_CONFIG_ID` and `CALENDAR_AUTH_CONFIG_ID` (or create separate integrations per service)

> Users who connected before Calendar scopes were added must disconnect and reconnect.

**Microsoft Outlook (optional):**

1. Composio dashboard → **Integrations → Outlook**
2. Create a new integration with these Microsoft Graph API scopes: `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`, `Calendars.Read.Shared`, `Contacts.ReadWrite`, `User.Read`, `MailboxSettings.Read`
3. Copy the generated **Auth Config ID** → set as `OUTLOOK_AUTH_CONFIG_ID`

---

## Quick Start

```bash
git clone <repo-url>
cd ai-assistant-suite3

npm run install:all                    # Node packages
cd backend && uv sync && cd ..         # Python packages

cp backend/.env.example backend/.env  # fill in API keys
npm run dev
# Frontend → http://localhost:3000
# Backend  → http://localhost:8000
```

For a production build:

```bash
bash res.sh
```

---

## Environment Variables

### `backend/.env` — Required

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (`sk-ant-api03-...`) |
| `COMPOSIO_API_KEY` | Composio platform API key (`ak_...`) |
| `GMAIL_AUTH_CONFIG_ID` | Composio Auth Config ID for Gmail OAuth (`ac_...`) |
| `CALENDAR_AUTH_CONFIG_ID` | Composio Auth Config ID for Calendar OAuth (`ac_...`) — can be same value as Gmail if both scopes are in one integration |
| `OUTLOOK_AUTH_CONFIG_ID` | *(optional)* Composio Auth Config ID for Outlook OAuth (`ac_...`) — required only if supporting non-Gmail users |

### `backend/.env` — Optional (AI & Agent)

| Variable | Default | Description |
|---|---|---|
| `MODEL_NAME` | `claude-opus-4-6` | Anthropic model for chat and email summariser |
| `SUGGESTIONS_MODEL_NAME` | `claude-haiku-4-5-20251001` | Lighter model used only for quick-action suggestion chips |
| `AGENT_MAX_TOKENS` | `4096` | Max output tokens per agent stream call |
| `MAX_TOOL_RESULT_CHARS` | `8000` | Characters kept from each Composio tool result before sending to the LLM (general tools) |
| `CALENDAR_TOOL_RESULT_CHARS` | `50000` | Higher character cap for calendar event list results — calendar events are structured data and need more room than email |
| `EMAIL_BODY_TRUNCATE_CHARS` | `500` | Characters kept from individual email body fields inside tool results |
| `MAX_HISTORY_TURNS` | `10` | Conversation turns retained per agent before older turns are trimmed |
| `SUGGESTION_CONTEXT_CHARS` | `1500` | Characters of last assistant response used as context for suggestion chips |
| `SUGGESTION_MAX_TOKENS` | `120` | Max tokens for the suggestion-chips LLM call |

### `backend/.env` — Optional (Email Summariser)

| Variable | Default | Description |
|---|---|---|
| `EMAIL_SUMMARIZER_MODE` | `always` | `off` · `always` · `smart` — see below |
| `EMAIL_SUMMARIZER_MODEL_NAME` | `claude-haiku-4-5-20251001` | Model used for the summariser — keep on a different model from the chat agent (`MODEL_NAME`) so they use separate TPM budgets |
| `EMAIL_SUMMARIZER_MAX_TOKENS` | `1024` | Max output tokens for the summariser LLM call |
| `EMAIL_SUMMARIZER_BODY_CHARS` | `800` | Max characters kept from each email body before summarising |
| `EMAIL_FETCH_LIMIT` | `30` | Max emails fetched per summariser run |
| `EMAIL_LOOKBACK_DAYS` | `14` | How many days back to look for unread emails |
| `EMAIL_SUMMARIZER_DB_PATH` | `data/email_summarizer.json` | Relative path (from `backend/`) to the TinyDB file used in `smart` mode |

#### `EMAIL_SUMMARIZER_MODE` values

| Mode | Behaviour |
|---|---|
| `off` | Disabled — no emails fetched on login |
| `always` | Runs on every login; processes all unread emails from the past `EMAIL_LOOKBACK_DAYS` days |
| `smart` | Only processes new emails (IDs tracked in TinyDB); skips if nothing new |

Use `smart` in production, `always` during development.

### `backend/.env` — Optional (SSE & Composio)

| Variable | Default | Description |
|---|---|---|
| `PENDING_EVENT_TTL` | `300` | Seconds to buffer trigger events while no SSE stream is connected |
| `SSE_KEEPALIVE_INTERVAL` | `20.0` | Seconds between SSE keepalive comments (prevents proxy timeouts) |
| `TOP_CONTACTS_LIMIT` | `15` | Contacts fetched from GOOGLECONTACTS for the agent user profile |
| `PROFILE_FETCH_WORKERS` | `5` | Thread pool size for parallel profile data fetches on login |
| `PROFILE_FETCH_TIMEOUT` | `10` | Per-future timeout (seconds) in the profile fetch pool |
| `CALENDAR_REMINDER_MINUTES` | `15` | Default minutes-before for the GOOGLECALENDAR_EVENT_STARTING_SOON trigger |

### `backend/.env` — Optional (Notifier & WhatsApp)

| Variable | Default | Description |
|---|---|---|
| `HTTP_REQUEST_TIMEOUT` | `10` | Timeout (seconds) for outbound HTTP calls (e.g. Twilio) |
| `WHATSAPP_SNIPPET_CHARS` | `200` | Max characters from a Gmail snippet included in WA trigger messages |
| `FRONTEND_URL` | `http://localhost:3000` | Allowed CORS origin + OAuth callback base URL. Set to your public domain in production. |
| `TWILIO_ACCOUNT_SID` | — | Twilio Account SID (from console dashboard) |
| `TWILIO_AUTH_TOKEN` | — | Twilio Auth Token |
| `TWILIO_WHATSAPP_FROM` | `whatsapp:+14155238886` | Sender number in `whatsapp:+E164` format |
| `TWILIO_SANDBOX_KEYWORD` | — | Join keyword shown in the WA settings panel (e.g. `dish-pen`) |

#### `TWILIO_WHATSAPP_FROM` — sandbox vs production

- **Sandbox (dev/testing):** Use `whatsapp:+14155238886` — Twilio's shared gateway. Recipients must send `join <TWILIO_SANDBOX_KEYWORD>` to `+1 415 523 8886` on WhatsApp once to opt in.
- **Production:** Use `whatsapp:+<your-approved-number>`. Requires WhatsApp Business API approval — apply via Twilio Console → **Messaging → Senders → WhatsApp Senders**.

> `TWILIO_WHATSAPP_FROM` (the *sender* number users see) and the sandbox opt-in gateway (`+1 415 523 8886`) are different numbers in sandbox mode. This is normal Twilio sandbox behaviour.

### `frontend/.env.local`

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**`NEXT_PUBLIC_API_URL`** — base URL the browser uses to reach the FastAPI backend. Defaults to `http://localhost:8000`. In production, set to your public backend domain. This variable is **baked in at build time** — rebuild the frontend after changing it.

---

## Build

### Development (hot-reload)

```bash
npm run dev   # frontend :3000 + backend :8000 concurrently
```

### Production rebuild

Choose the right script based on what changed:

| Script | When to use |
|---|---|
| `bash res.sh` | Full rebuild — both services, all dependencies |
| `bash bk.sh` | Python edits or `.env` changes — backend only, no dep sync |
| `bash bk2.sh` | `pyproject.toml` changed or new Python packages added |
| `bash fn.sh` | TSX / TS / CSS edits — frontend only, no `npm install` |
| `bash fn2.sh` | New Node packages added (`package.json` changed) |

`res.sh` — 9 steps: kill ports → **parallel** `uv sync` + `npm install` → localStorage key check → smart `.next` wipe (only if tsconfig/tailwind/package.json changed) → `npm run build` → start backend → start frontend → polling health checks. Exits non-zero on failure. Logs: `logs/app.log`.

> All scripts use **polling health checks** (ready in actual time, not a fixed sleep) and a **smart `.next` cache** — component-only edits with `fn.sh` skip the full wipe and build in ~15s instead of ~45s.

Logs → `logs/app.log`. Tail with `tail -f logs/app.log`.
Log file is trimmed to the last 800 lines on each run.

---

## Deploy

### Local Machine (Production Mode)

```bash
bash res.sh
# App at http://localhost:3000
```

Stop services: `lsof -ti :3000,:8000 | xargs kill -9 2>/dev/null || true`

### VPS / Linux Server

#### 1. Install prerequisites

```bash
# Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs python3.11 python3.11-venv nginx

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.cargo/env
```

#### 2. Clone, configure, build

```bash
git clone <repo-url> /opt/ai-assistant-suite3
cd /opt/ai-assistant-suite3
cp backend/.env.example backend/.env   # fill in all variables

npm run install:all
cd backend && uv sync && cd ..
cd frontend && npm run build && cd ..
```

#### 3. Process management with PM2

```bash
npm install -g pm2
```

`ecosystem.config.js`:

```js
module.exports = {
  apps: [
    {
      name: "assistant-backend",
      cwd: "./backend",
      script: "uv",
      args: "run uvicorn app.main:app --host 0.0.0.0 --port 8000",
    },
    {
      name: "assistant-frontend",
      cwd: "./frontend",
      script: "npm",
      args: "start",
      env: { PORT: "3000" }
    }
  ]
};
```

```bash
pm2 start ecosystem.config.js
pm2 save && pm2 startup   # follow printed command
```

#### 4. Nginx reverse proxy

```nginx
server {
    listen 80;
    server_name assistant.yourdomain.com;

    location / {
        proxy_pass         http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection 'upgrade';
        proxy_set_header   Host $host;
    }

    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_buffering    off;   # required for SSE
        proxy_cache        off;
        proxy_read_timeout 3600s;
    }

    location /health { proxy_pass http://127.0.0.1:8000; }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/ai-assistant /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# HTTPS
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d assistant.yourdomain.com

# Firewall
sudo ufw allow 22,80,443/tcp && sudo ufw enable
```

### Production `backend/.env`

```env
ANTHROPIC_API_KEY=sk-ant-...
COMPOSIO_API_KEY=...
GMAIL_AUTH_CONFIG_ID=ac_...
CALENDAR_AUTH_CONFIG_ID=ac_...
OUTLOOK_AUTH_CONFIG_ID=ac_...    # optional — only if supporting Outlook users

MODEL_NAME=claude-opus-4-6
FRONTEND_URL=https://assistant.yourdomain.com
EMAIL_SUMMARIZER_MODE=smart

# WhatsApp (optional)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_SANDBOX_KEYWORD=dish-pen
```

`frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=https://assistant.yourdomain.com
```

> Rebuild the frontend after changing `NEXT_PUBLIC_*` variables.

### Webhook Setup for Composio Triggers

#### Production

1. Composio dashboard → **Settings → Webhooks** → set URL to `https://assistant.yourdomain.com/api/triggers/webhook`
2. Subscribe users via `POST /api/triggers/subscribe`

#### Local Development

```bash
ngrok http 8000
# Use the printed URL in Composio → Settings → Webhooks
```

> ngrok URLs change on each restart unless you have a paid reserved domain.

### Deploy Checklist

- [ ] All required `backend/.env` variables set for production
- [ ] `FRONTEND_URL` matches the actual public domain (CORS)
- [ ] `NEXT_PUBLIC_API_URL` points to the public backend URL and frontend is rebuilt
- [ ] Composio webhook URL updated to production domain
- [ ] HTTPS active; Nginx `proxy_buffering off` on SSE routes
- [ ] PM2 startup registered (`pm2 startup` + `pm2 save`)
- [ ] `backend/data/` directory writable — TinyDB stores here: `profile_cache.json`, `token_store.json`, `history_store.json`, `email_summarizer.json`
- [ ] `GET /health` returns HTTP 200

---

## Project Structure

```
ai-assistant-suite3/
│
├── backend/                          # FastAPI + Python (uv)
│   ├── app/
│   │   ├── main.py                   # Entry point — FastAPI app, CORS, SSL fix
│   │   ├── constants.py              # Application-wide string constants and field names
│   │   ├── config/settings.py        # pydantic-settings — reads backend/.env; all tuneable values
│   │   ├── models/schemas.py         # Pydantic request/response models
│   │   ├── core/
│   │   │   ├── agent.py              # Streaming agentic loop (SSE); four-agent system prompts
│   │   │   ├── composio_client.py    # Composio v1: tool fetch/execute + trigger management + provider-aware profile fetchers
│   │   │   ├── email_summarizer.py   # Login-triggered email action-item summariser
│   │   │   ├── notifier.py           # Twilio WhatsApp send helper + trigger formatter
│   │   │   ├── profile_store.py      # TinyDB persistent profile cache with provider segregation (data/profile_cache.json)
│   │   │   ├── history_store.py      # TinyDB chat history persistence (data/history_store.json)
│   │   │   ├── session_store.py      # In-memory session store keyed by email; auto-restores profile + history
│   │   │   ├── token_store.py        # TinyDB session token store (data/token_store.json)
│   │   │   └── trigger_store.py      # Per-user asyncio.Queue fanout for SSE delivery
│   │   └── api/routes/
│   │       ├── auth.py               # POST /api/auth/initiate · GET /api/auth/status/{email} · POST /api/auth/logout
│   │       ├── chat.py               # POST /api/chat/message → SSE stream (token-protected)
│   │       ├── notifications.py      # WhatsApp settings + test endpoints (token-protected)
│   │       ├── settings.py           # GET/POST /api/settings — backend env var management
│   │       └── triggers.py           # Trigger CRUD + webhook receiver + SSE stream (token-protected)
│   └── pyproject.toml
│
├── frontend/                         # Next.js 15 (App Router, TypeScript, Tailwind)
│   ├── app/
│   │   ├── page.tsx                  # Main page — auth gate + chat layout + toast mount
│   │   └── auth/callback/page.tsx    # Google/Microsoft OAuth return handler
│   ├── components/
│   │   ├── Auth/ConnectButton.tsx    # Email input + Google/Microsoft connect form (auto-detects provider)
│   │   ├── Chat/
│   │   │   ├── ChatWindow.tsx        # Scrollable message list + personalised empty state
│   │   │   ├── MessageBubble.tsx     # User/assistant bubbles + markdown renderer
│   │   │   ├── MessageInput.tsx      # Textarea + voice input + agent selector + send
│   │   │   └── SuggestionsPane.tsx   # Quick-actions sidebar (localStorage-persisted)
│   │   ├── Settings/
│   │   │   └── SettingsPanel.tsx     # Slide-in panel: view + update backend .env vars via UI
│   │   ├── ui/
│   │   │   ├── icons.tsx             # Shared SVG icon components (Spinner, BellIcon, SendIcon, etc.)
│   │   │   └── MarkdownContent.tsx   # Shared markdown renderer; EditableBlock for editable code fences
│   │   └── Notifications/
│   │       ├── NotificationDrawer.tsx  # Bell icon + drawer; processing progress bar + timer
│   │       ├── NotificationListener.tsx # EventSource consumer; maps SSE events to state
│   │       ├── TriggerToast.tsx      # Slide-in toast — spinner/shimmer while processing
│   │       └── WhatsAppSettings.tsx  # WA settings dropdown (phone, toggle, send test)
│   └── lib/
│       ├── agents.ts                 # Agent metadata + AgentColors tokens (workspace/gmail/calendar/outlook)
│       ├── api.ts                    # Backend fetch calls + SSE async generator + token management
│       ├── constants.ts              # Frontend magic values (timeouts, limits, storage keys, URLs, badge config)
│       ├── icons.ts                  # autoIcon() helper — derives emoji from trigger/action name patterns
│       ├── styles.ts                 # UI namespace: shared Tailwind class strings (btn, input, badge, card, alert)
│       └── types.ts                  # Shared TypeScript types
│
├── res.sh                            # Full rebuild — 9 steps, health-checked (replaces restart.sh)
├── bk.sh                             # Backend-only restart (Python edits, no dep changes)
├── bk2.sh                            # Backend restart + uv sync (pyproject.toml changed)
├── fn.sh                             # Frontend-only rebuild (TSX/TS/CSS edits, no new packages)
├── fn2.sh                            # Frontend rebuild + npm install (new Node packages)
└── package.json                      # Root: concurrently dev script
```

---

## Architecture

### Authentication & Session Flow

```
User enters email address
  → Frontend detects domain: @gmail.com/@googlemail.com → Google; otherwise → Outlook
  → POST /api/auth/initiate (agent_type: "gmail" or "outlook")
  → Backend derives user_id: re.sub(r'[^a-zA-Z0-9_-]', '_', email.lower())
  → Selects auth config: Gmail → GMAIL_AUTH_CONFIG_ID; Outlook → OUTLOOK_AUTH_CONFIG_ID
  → Check existing Composio connection
      ├─ Active → {connected: true, session_token: "<256-bit token>"} → chat opens; email summariser triggered
      └─ None   → {auth_url: "..."} → frontend redirects to Google/Microsoft OAuth
          → User consents
          → /auth/callback?email=... stores user_email in localStorage → redirects to /
          → POST /api/auth/initiate again → returns session_token on success
          → Email summariser triggered after OAuth (both Gmail and Outlook)
```

Sessions are **email-keyed** in-memory. Session tokens are stored in TinyDB (`data/token_store.json`) and persist across restarts. Chat history is also persisted to TinyDB (`data/history_store.json`) and automatically restored when a session is first created after a restart. User profiles are cached in TinyDB (`data/profile_cache.json`) with a `provider` field for segregation. Sign-out calls `POST /api/auth/logout` which revokes the token and clears all user data.

### Agent Architecture

Each chat message carries `agent_type` (`"gmail"` | `"calendar"` | `"workspace"` | `"outlook"`) which controls:

| Dimension | Gmail Agent | Calendar Agent | Workspace Agent | Outlook Agent |
|---|---|---|---|---|
| Provider | Google | Google | Google | Microsoft |
| Composio toolkit | `["gmail", "googlecontacts"]` | 10 calendar tools + contacts | 11 Gmail + 10 calendar (21 total) | 31 curated Outlook tools |
| System prompt | `GMAIL_SYSTEM_PROMPT` | `CALENDAR_SYSTEM_PROMPT` | `WORKSPACE_SYSTEM_PROMPT` | `OUTLOOK_SYSTEM_PROMPT` |
| History | `session.gmail_messages` | `session.calendar_messages` | `session.workspace_messages` | `session.outlook_messages` |
| Available to | Gmail users | Gmail users | Gmail users | Non-Gmail users |

The **workspace** agent is a Google superset — use it for cross-domain tasks (e.g. "email everyone on tomorrow's meeting"). The **outlook** agent covers email + calendar + contacts in a single agent with 31 curated tools (from 200+ available).

**Scheduling safeguards (Calendar, Workspace, and Outlook agents):**
- **3-stage scheduling workflow** — Stage 1: fillable template; Stage 2: conflict detection with Option A/B; Stage 3: create event with meeting link (Google Meet or Microsoft Teams)
- **Rescheduling conflicts** — when a conflict is detected, the agent presents both the conflicting event and the proposed new slot, then waits for explicit user approval before rescheduling. Automatic rescheduling without confirmation is blocked.
- **Destructive operations** — `GOOGLECALENDAR_CLEAR_CALENDAR` and `GOOGLECALENDAR_CALENDARS_DELETE` always require explicit user confirmation before execution.

**Agentic loop ([`backend/app/core/agent.py`](backend/app/core/agent.py))**:

```
User message + agent_type  ("gmail" | "calendar" | "workspace" | "outlook")
  → Load Composio toolkit (+ inject send_whatsapp_notification custom tool)
  → Stream LLM response (adaptive thinking enabled)
  → if stop_reason == "tool_use":
      → If send_whatsapp_notification: handle locally via notifier.py
      → Otherwise: execute via Composio
          → Calendar events: strip to essential fields; cap at settings.calendar_tool_result_chars (50 K)
          → Other tools: truncate to settings.max_tool_result_chars (8 K)
      → Append tool_results as next user turn → loop
  → Trim history to last settings.max_history_turns turns before each API call
  → Save history to TinyDB (history_store.py) before yielding "done"
  → Yield SSE events:
      { "type": "text",       "content": "<delta>" }
      { "type": "tool_start", "name": "GMAIL_FETCH_EMAILS" }
      { "type": "tool_end",   "name": "GMAIL_FETCH_EMAILS", "success": true }
      { "type": "done" }
      { "type": "error",      "message": "..." }
```

> Thinking blocks are excluded from serialised history to prevent context bloat.

### Email Action Summariser

Triggered on every user login (configurable via `EMAIL_SUMMARIZER_MODE`) for both Gmail and Outlook users:

1. Publishes an `is_processing: true` notification event immediately — browser shows spinner, shimmer header, and indeterminate progress bar in real time
2. Fetches unread emails from the past `EMAIL_LOOKBACK_DAYS` days (Gmail: `GMAIL_FETCH_EMAILS`; Outlook: `OUTLOOK_LIST_MESSAGES`)
3. Formats with provider-specific metadata (Gmail: labels/categories/importance; Outlook: importance/flag/classification/categories)
4. Three-stage LLM prompt with provider-specific Step 1 signal pre-filter → inclusion decision → exclusion confirmation
5. Produces two HTML tables: **Actionable Items** and **Email Reference**; duplicate action items are merged before output
6. Reorders Claude's output to guarantee section order: **Actionable Items → Email Reference → Additional Notes**
7. Appends a backend-generated **Summary Statistics** table (emails scanned, lookback period, mode, provider, inclusion/exclusion rules)
8. Saves result as an HTML-formatted draft in the user's provider (`GMAIL_CREATE_EMAIL_DRAFT` or `OUTLOOK_CREATE_DRAFT`)
9. Publishes an `agent_complete` event — replaces the processing indicator with real results

On page reload, stale `is_processing` notifications are filtered out of localStorage automatically (they can never resolve after a reload).

### Real-time Trigger Notifications

Runs independently of the agent loop — no AI model involved:

```
Composio detects event (new email, calendar change, etc.)
  → POST /api/triggers/webhook
  → Resolve user email from metadata.client_unique_user_id
  → trigger_store.publish(email, event_payload)
  → Fanout to all open SSE queues for that user → TriggerToast slide-in
  → If WA enabled: asyncio.create_task(send_whatsapp(...))  ← fire-and-forget
  → Keepalive comment every settings.sse_keepalive_interval s to hold SSE open
```

Events published while no SSE stream is connected are buffered for up to `PENDING_EVENT_TTL` seconds and delivered the moment a stream connects.

### Frontend SSE

Chat uses `fetch` + `ReadableStream` (not `EventSource`) because the endpoint is `POST`. `streamMessage()` in `lib/api.ts` is an async generator yielding typed `SSEEvent` objects.

### Persistent Profile Cache

`profile_store.py` — TinyDB store at `backend/data/profile_cache.json`. Each record includes a `provider` field (`"gmail"` or `"outlook"`) for clear segregation. Persists per-user display name, timezone, locale, calendars, and frequent contacts across backend restarts. `SessionStore.get_or_create()` calls `load_profile()` so sessions auto-restore cached data on the first request after a restart — no re-fetch needed.

Profile data is fetched from provider-specific APIs:
- **Gmail users**: `GMAIL_GET_PROFILE`, `GOOGLECALENDAR_SETTINGS_LIST`, `GOOGLECALENDAR_LIST_CALENDARS`, `GOOGLECONTACTS_LIST_CONTACTS`
- **Outlook users**: `OUTLOOK_GET_PROFILE`, `OUTLOOK_GET_MAILBOX_SETTINGS` (Windows TZ → IANA conversion), `OUTLOOK_LIST_CALENDARS`, `OUTLOOK_LIST_USER_CONTACTS`

`_build_profile_block()` adapts the system prompt block based on the provider — Gmail users see Gmail-specific fields (message counts, thread counts); Outlook users see Outlook-specific fields (job title, office, working hours, working days). Frequent contacts are injected so agents can resolve names without extra API round-trips.

### Markdown Renderer & Editable Pre-fill Blocks

`frontend/components/ui/MarkdownContent.tsx` — shared zero-dependency renderer:

| Input | Output |
|---|---|
| ` ```code fence``` ` | **`EditableBlock`** — editable `<textarea>` with "Use this ↗" button (pastes into message input) |
| `\|`-delimited rows | Full `<table>` with styled header and alternating rows |
| `**bold**` / `*italic*` / `` `code` `` | `<strong>` / `<em>` / `<code>` |
| `- ` / `* ` bullet lines | `<ul><li>` |
| `1. ` / `  3. ` numbered lines | `<ol start={N}>` — preserves actual sequence number, supports indented items; numbering never resets mid-list |
| `# ` / `## ` heading lines | `<h3>` / `<h4>` |

`MessageBubble.tsx` passes `onEditableBlock` → clicking "Use this ↗" calls `onSuggestion(editedText, agentType)` which pre-fills the message input. Agents use the shared formatting instructions to present structured input forms (meeting details, email drafts, tasks) as editable code blocks.

### Constants & Configuration

| File | Purpose |
|---|---|
| `backend/app/config/settings.py` | All tuneable numeric limits, timeouts, model names, and feature flags — overridable via `backend/.env` |
| `backend/app/constants.py` | Non-configurable string constants: field names, message templates, payload wrapper keys |
| `frontend/lib/constants.ts` | Frontend magic values: timeouts, localStorage key helpers, preview limits, speech locale, URLs, badge config, sidebar width |
| `frontend/lib/styles.ts` | `UI` namespace — single source of truth for shared Tailwind class strings (`btn`, `input`, `badge`, `card`, `alert`) |
| `frontend/lib/agents.ts` | `AGENT_META` map — per-agent label, icon, and `AgentColors` Tailwind tokens (workspace/gmail/calendar/outlook) |
| `frontend/lib/icons.ts` | `autoIcon()` helper — derives an emoji from a trigger or action name using regex pattern matching |
| `frontend/components/ui/icons.tsx` | Shared SVG icon components — import from here instead of writing inline SVGs |
| `frontend/tailwind.config.ts` | Tailwind extension: custom keyframes (`shimmer`, `indeterminate`, `ring`) + `spacing.sidebar` (`272px`) |

---

## API Reference

### Authentication & Chat

| Method | Path | Body / Params | Description |
|---|---|---|---|
| `POST` | `/api/auth/initiate` | `{email, callback_url?, agent_type?}` | Start Google/Microsoft OAuth or confirm existing connection. Returns `session_token` when connected. |
| `GET` | `/api/auth/status/{email}` | — | Poll connection status (Gmail+Calendar or Outlook). Returns `session_token` when connected. |
| `POST` | `/api/auth/logout` | `{email}` | Revoke session token and disconnect |
| `POST` | `/api/chat/message` | `{email, message, agent_type, session_token}` | Send message — returns SSE stream. Requires valid token. |
| `POST` | `/api/chat/clear` | `{email, agent_type?, session_token}` | Clear history (one or all agents). Requires valid token. |
| `GET` | `/health` | — | Liveness check |

### Trigger Management

| Method | Path | Body / Params | Description |
|---|---|---|---|
| `GET` | `/api/triggers/available` | — | List all supported trigger definitions |
| `GET` | `/api/triggers/active/{email}` | — | List active subscriptions with IDs |
| `POST` | `/api/triggers/subscribe` | `{email, trigger_name, config?, session_token}` | Enable a trigger. Requires valid token. |
| `POST` | `/api/triggers/unsubscribe` | `{email, trigger_subscription_id, session_token}` | Disable a trigger. Requires valid token. |
| `POST` | `/api/triggers/webhook` | Composio payload | Webhook receiver (called by Composio) |
| `GET` | `/api/triggers/stream/{email}` | `?token=<session_token>` | Long-lived SSE stream for toast notifications. Requires valid token. |

### WhatsApp Notifications

| Method | Path | Body / Params | Description |
|---|---|---|---|
| `GET` | `/api/notifications/whatsapp/{email}` | — | Fetch saved WhatsApp settings |
| `POST` | `/api/notifications/whatsapp` | `{email, whatsapp_number, enabled, session_token}` | Save phone number and toggle. Requires valid token. |
| `POST` | `/api/notifications/whatsapp/test` | `{email, whatsapp_number, session_token}` | Send a test message. Requires valid token. |

### Settings

| Method | Path | Body / Params | Description |
|---|---|---|---|
| `GET` | `/api/settings` | — | List all backend env vars (sensitive values masked) |
| `POST` | `/api/settings` | `{updates: {key: value}}` | Update one or more backend env vars at runtime |

---

## Trigger System

### Gmail Triggers

| Slug | Label |
|---|---|
| `GMAIL_NEW_EMAIL_EVENT` | 📨 New Email Received |
| `GMAIL_MESSAGE_SENT` | 📤 Email Sent |

### Google Calendar Triggers

| Slug | Label |
|---|---|
| `GOOGLECALENDAR_EVENT_CREATED` | ✅ Event Created |
| `GOOGLECALENDAR_EVENT_UPDATED` | ✏️ Event Updated |
| `GOOGLECALENDAR_EVENT_CANCELLED` | ❌ Event Cancelled |
| `GOOGLECALENDAR_ATTENDEE_RESPONSE_CHANGED` | 🔔 Attendee Response |
| `GOOGLECALENDAR_EVENT_STARTING_SOON` | ⏰ Starting Soon |
| `GOOGLECALENDAR_CALENDAR_EVENT_SYNC` | 🔄 Event Sync |

---

## WhatsApp Notifications

### How It Works

WhatsApp notifications are delivered in three ways:

1. **Trigger events** — when Composio fires a webhook (new email, calendar change), the backend forwards a formatted message to the user's WhatsApp number (fire-and-forget)
2. **Email action summary** — after the login summariser creates a Gmail draft, the action-item table is sent to WhatsApp in parallel
3. **On-demand from agents** — any agent can call the built-in `send_whatsapp_notification` tool when asked to notify you

### Setup

1. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, and `TWILIO_SANDBOX_KEYWORD` in `backend/.env`
2. **Sandbox opt-in (one-time per recipient):** send `join <TWILIO_SANDBOX_KEYWORD>` to `+1 415 523 8886` on WhatsApp — the WA settings panel shows this instruction automatically
3. In the app header → **WA** → enter phone number in E.164 format → toggle on → **Save**
4. Click **Send test** to verify delivery

> **Sandbox vs production:** `+1 415 523 8886` is Twilio's shared opt-in gateway; `TWILIO_WHATSAPP_FROM` is the sender number users see. In sandbox mode these are different — that is expected. For production, apply for WhatsApp Business API approval via Twilio Console → **Messaging → Senders → WhatsApp Senders**.

### Phone Number Format (E.164)

| Country | Example |
|---|---|
| India | `+919876543210` |
| US | `+14155552671` |
| UK | `+447911123456` |

---

## Development

```bash
npm run dev          # both services with hot-reload
npm run dev:frontend # Next.js only → :3000
npm run dev:backend  # uvicorn only → :8000
bash res.sh          # full production rebuild (both services)
bash bk.sh           # backend only (Python edits, .env changes)
bash bk2.sh          # backend + uv sync (dep changes)
bash fn.sh           # frontend only (TSX/TS/CSS edits)
bash fn2.sh          # frontend + npm install (new Node packages)
tail -f logs/app.log # stream logs
```

**localStorage keys** — quick-action defaults are versioned (`quick_actions_gmail_vN`, `quick_actions_calendar_vN`); `res.sh` / `fn.sh` auto-bumps the version when defaults change — never bump manually. `sidebar_width` stores the drag-resized sidebar width (180–520 px).

**Suggestion label/text updates** — on load, `SuggestionsPane` refreshes the `label` and `text` of any stored suggestion whose ID matches a current default, so renaming or updating a suggestion prompt is always picked up after the next `res.sh` rebuild without needing an ID change or version bump.

**Quick-action prompt authoring note** — suggestion prompts sent to the model must be written in plain first-person user language. Avoid embedding raw tool names (e.g. `GMAIL_FETCH_EMAILS`), explicit API query strings, or phrases like "silently resolve" in prompt text. The model's prompt-injection detection treats these patterns as suspicious injected instructions and refuses to act. The workspace quick action **w7 "Share Action Items - WhatsApp (via Twilio)"** was updated for this reason: it now reads as a natural user request, letting the model choose the appropriate tools itself.

**Tuning limits without code changes** — all character limits, timeouts, model names, and fetch counts live in `backend/.env` via `backend/app/config/settings.py`. No code changes needed to adjust these in production.

---

## Known Platform Notes

### macOS / Python 3.13 (Homebrew)

`httpx` cannot verify TLS with the system Python 3.13 cert store on macOS. Fixed in `backend/app/main.py`:

```python
import truststore
truststore.inject_into_ssl()
```

**Do not remove this call.** `truststore` is in `pyproject.toml`.

### Composio SDK

- `dangerously_skip_version_check=True` is required on `composio.tools.execute()` — omitting it raises `ToolVersionRequiredError`
- `GMAIL_AUTH_CONFIG_ID` / `CALENDAR_AUTH_CONFIG_ID` must cover the correct API scopes. Users who authenticated before Calendar scopes were added must re-connect.

---

## Security & Known Limitations

This app is designed for personal/development use. The following limitations apply before deploying to a production environment with multiple users.

### In-memory session store (no TTL)

Runtime session state (active agent context, WhatsApp settings) is held in a Python `dict` keyed by email. Sessions never expire during a run. A backend restart clears in-memory state, but chat history and session tokens are both persisted in TinyDB and automatically restored on first request after restart.

**Remaining gap:** WhatsApp number and enabled-flag are still in-memory only (not persisted). Re-entering them after a backend restart is required until a `wa_store.py` is added.

### Webhook email validation

`POST /api/triggers/webhook` resolves the user from `metadata.client_unique_user_id` in the Composio payload without verifying a shared secret or HMAC signature. Any HTTP client that can reach the endpoint can inject fake trigger events.

**Mitigation for production:** add Composio webhook signature verification or restrict the endpoint to Composio's IP ranges.

### Phone number validation

WhatsApp numbers are validated and normalised to E.164 format (`+<country_code><number>`) before every send. Invalid numbers return a descriptive error surfaced in the bell drawer and chat. Twilio HTTP error responses are parsed for the specific error code and `more_info` URL.

### No rate limiting on webhook or chat endpoints

The `/api/triggers/webhook` and `/api/chat/message` endpoints have no rate limiting. High-frequency webhook delivery or rapid chat requests could exhaust Anthropic API quota or memory.

### Markdown renderer XSS

`MessageBubble.tsx` builds HTML strings by concatenation and sets them via `dangerouslySetInnerHTML`. Content rendered via the markdown renderer (assistant output) is attacker-controlled if the LLM or Composio tool results return crafted HTML/JS.

**Mitigation:** consider replacing with a well-maintained renderer (e.g. `react-markdown` + `remark-gfm`) that sanitises output.

### WhatsApp sandbox limitations

The Twilio sandbox (`whatsapp:+14155238886`) requires each recipient to opt in once by sending a join message. Messages to numbers that have not opted in are silently dropped. Sandbox is not suitable for external users.

### CORS wildcard in development

The backend `allow_methods=["*"]` allows all HTTP methods from the configured `FRONTEND_URL` origin. Tighten to `["GET", "POST", "OPTIONS"]` for production.

---

*For developer configuration and architecture internals, see [CLAUDE.md](./CLAUDE.md).*
