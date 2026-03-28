/**
 * Application-wide frontend constants.
 *
 * Anything that appears as a magic number or literal string in more than one
 * place — or is a domain-meaningful value — belongs here.
 */

// ── Timing ────────────────────────────────────────────────────────────────────

/** Delay (ms) before moving focus to the label input in the quick-action form */
export const FOCUS_DELAY_MS = 50;

/** Delay (ms) before showing the greeting after OAuth callback completes */
export const GREETING_DISPLAY_DELAY_MS = 800;

/** Duration (ms) matching the toast slide-out CSS transition */
export const TOAST_SLIDE_OUT_MS = 350;

// ── Notification persistence ──────────────────────────────────────────────────

/** How many days to retain notifications in localStorage */
export const NOTIFICATION_RETENTION_DAYS = 7;

/** Computed milliseconds constant derived from NOTIFICATION_RETENTION_DAYS */
export const NOTIFICATION_RETENTION_MS = NOTIFICATION_RETENTION_DAYS * 24 * 60 * 60 * 1000;

// ── Quick-action form limits ──────────────────────────────────────────────────

/** Max characters allowed in a quick-action label */
export const QUICK_ACTION_LABEL_MAX = 24;

/** Max characters allowed in a quick-action prompt body */
export const QUICK_ACTION_TEXT_MAX = 200;

// ── Toast / notification preview limits ──────────────────────────────────────

/** Max chars shown for the "From" field in the trigger toast */
export const TOAST_FROM_PREVIEW_CHARS = 24;

/** Max chars shown for subject / event title in the trigger toast */
export const TOAST_SUBJECT_PREVIEW_CHARS = 26;

/** Max chars shown for error body preview in the trigger toast */
export const TOAST_ERROR_PREVIEW_CHARS = 100;

// ── Speech recognition ────────────────────────────────────────────────────────

/** BCP-47 language tag used for the Web Speech API */
export const SPEECH_RECOGNITION_LANG = "en-US";

// ── localStorage key helpers ──────────────────────────────────────────────────
// Quick-action storage keys are versioned by restart.sh — do not change manually.

export const STORAGE_KEY_USER_EMAIL    = "user_email";
export const STORAGE_KEY_PENDING_EMAIL = "pending_email";
export const STORAGE_KEY_SESSION_TOKEN = "session_token";

/** Returns the per-user notification storage key */
export const notificationsStorageKey = (email: string) => `notifications:${email}`;

/** Returns the per-user display-name storage key */
export const displayNameStorageKey = (email: string) => `display_name:${email}`;

// ── Auth callback polling ─────────────────────────────────────────────────────

/** Maximum number of status-poll attempts before declaring a timeout */
export const AUTH_POLL_MAX_ATTEMPTS = 20;

/** Interval (ms) between auth status poll retries on success path */
export const AUTH_POLL_INTERVAL_MS = 1_500;

/** Interval (ms) between auth status poll retries after a network error */
export const AUTH_POLL_RETRY_MS = 2_000;

/** Delay (ms) before redirecting to chat after auth completes */
export const AUTH_REDIRECT_DELAY_MS = 800;

// ── Notification drawer ───────────────────────────────────────────────────────

/** Interval (ms) for the elapsed-time ticker while a notification is processing */
export const ELAPSED_TIME_TICK_MS = 1_000;

/** Duration (ms) the bell rings after a new notification arrives */
export const BELL_RING_DURATION_MS = 2_500;

/** Max chars shown for error body preview in the notification drawer */
export const NOTIFICATION_BODY_PREVIEW_CHARS = 80;

/** Max chars shown for email snippet preview in the notification drawer */
export const NOTIFICATION_SNIPPET_PREVIEW_CHARS = 120;

// ── Trigger name prefixes ─────────────────────────────────────────────────────

/** Prefix shared by all Gmail trigger slugs */
export const TRIGGER_PREFIX_GMAIL = "GMAIL_";

/** Prefix shared by all Google Calendar trigger slugs */
export const TRIGGER_PREFIX_GOOGLECAL = "GOOGLECAL";

// ── Typing indicator ──────────────────────────────────────────────────────────

/** Per-dot animation-delay step (seconds) for the three-dot typing indicator */
export const TYPING_INDICATOR_STAGGER_S = 0.15;

// ── SSE parsing ───────────────────────────────────────────────────────────────

/** Line prefix for SSE data events */
export const SSE_DATA_PREFIX = "data: ";

// ── Keyboard keys ─────────────────────────────────────────────────────────────

export const KEY_ENTER  = "Enter";
export const KEY_ESCAPE = "Escape";

// ── External URLs ─────────────────────────────────────────────────────────────

/** Base URL for Gmail label/search deep-links */
export const GMAIL_SEARCH_BASE_URL = "https://mail.google.com/mail/u/0/#search";

// ── API paths ─────────────────────────────────────────────────────────────────

/** Path prefix for the triggers SSE stream (appended with /{email}) */
export const API_TRIGGERS_STREAM_PATH = "/api/triggers/stream";

// ── Notification badge ────────────────────────────────────────────────────────

/** Unread count above which the badge shows the overflow display string */
export const UNREAD_BADGE_MAX = 9;

/** String shown in the unread badge when count exceeds UNREAD_BADGE_MAX */
export const UNREAD_BADGE_DISPLAY = "9+";

// ── Layout ────────────────────────────────────────────────────────────────────

/** Width in pixels of the left sidebar (must match tailwind.config `spacing.sidebar`) */
export const SIDEBAR_WIDTH_PX = 272;
