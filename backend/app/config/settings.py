from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str
    model_name: str = "claude-opus-4-6"
    # Lighter model used only for suggestion chips generation
    suggestions_model_name: str = "claude-haiku-4-5-20251001"
    composio_api_key: str
    gmail_auth_config_id: str
    calendar_auth_config_id: str
    frontend_url: str = "http://localhost:3000"

    # ── Agent limits ──────────────────────────────────────────────────────────
    agent_max_tokens: int = 8192
    max_tool_result_chars: int = 25_000
    # Higher limit for calendar list results (events are structured data, not free-text)
    calendar_tool_result_chars: int = 50_000
    # Characters truncated from individual email body fields inside tool results
    email_body_truncate_chars: int = 1500
    max_history_turns: int = 10
    # Characters of last assistant response fed into the suggestions prompt
    suggestion_context_chars: int = 1_500
    suggestion_max_tokens: int = 240

    # ── Email Summarizer ──────────────────────────────────────────────────────
    # Controls the background email summarizer triggered on login.
    # Values: "off" | "always" | "smart"
    #   off    — feature completely disabled
    #   always — summarize on every login regardless of prior runs
    #   smart  — only summarize emails not previously processed (tracks IDs)
    email_summarizer_mode: str = "always"
    # Dedicated model for the summarizer — uses Haiku by default so it runs
    # on a separate TPM budget and does not compete with the chat agent.
    email_summarizer_model_name: str = "claude-haiku-4-5-20251001"
    email_summarizer_max_tokens: int = 16_384
    # Read timeout (seconds) for the summariser LLM call — must be high enough
    # for 50 emails × 16K output tokens (can take 2–3 min on busy models)
    email_summarizer_read_timeout: int = 300
    # Max characters kept from each email body before sending to the summarizer
    email_summarizer_body_chars: int = 1600
    # How many emails to fetch per summarizer run
    email_fetch_limit: int = 30
    # How many days back the summarizer looks for unread emails
    email_lookback_days: int = 14
    # Relative path (from backend working directory) for the TinyDB file
    email_summarizer_db_path: str = "data/email_summarizer.json"

    # ── SSE / Trigger store ───────────────────────────────────────────────────
    # Seconds to buffer undelivered trigger events when no SSE stream is open
    pending_event_ttl: int = 300
    # Seconds between SSE keepalive comments (prevents proxy timeouts)
    sse_keepalive_interval: float = 20.0

    # ── Composio / profile fetch ──────────────────────────────────────────────
    # Contacts returned from GOOGLECONTACTS_LIST_CONTACTS
    top_contacts_limit: int = 25
    # ThreadPoolExecutor size used for parallel profile fetches
    profile_fetch_workers: int = 5
    # Per-future timeout (seconds) inside the profile fetch pool
    profile_fetch_timeout: int = 10
    # Default minutes-before for the GOOGLECALENDAR_EVENT_STARTING_SOON trigger
    calendar_reminder_minutes: int = 15

    # ── Notifier ─────────────────────────────────────────────────────────────
    # Timeout (seconds) for outbound HTTP requests (e.g. Twilio)
    http_request_timeout: int = 10
    # Max characters from a Gmail snippet included in WhatsApp messages
    whatsapp_snippet_chars: int = 200

    # ── Twilio WhatsApp ───────────────────────────────────────────────────────
    # Leave empty to disable WhatsApp notifications entirely.
    # Dev sandbox FROM: whatsapp:+14155238886
    twilio_account_sid: str = ""
    twilio_auth_token:  str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"  # sandbox default
    twilio_sandbox_keyword: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
