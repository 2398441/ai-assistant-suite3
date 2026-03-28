import { SSEEvent, AgentType } from "./types";
import { SSE_DATA_PREFIX, STORAGE_KEY_SESSION_TOKEN } from "./constants";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Session token helpers ──────────────────────────────────────────────────────

function getStoredToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(STORAGE_KEY_SESSION_TOKEN) ?? "";
}

export function storeSessionToken(token: string): void {
  localStorage.setItem(STORAGE_KEY_SESSION_TOKEN, token);
}

export function clearSessionToken(): void {
  localStorage.removeItem(STORAGE_KEY_SESSION_TOKEN);
}

// ---------- Auth ----------

export async function initiateAuth(
  email: string,
  callbackUrl?: string,
  agentType: AgentType = "gmail"
): Promise<{ connected: boolean; auth_url?: string; session_token?: string }> {
  const res = await fetch(`${API_URL}/api/auth/initiate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      callback_url: callbackUrl,
      agent_type: agentType,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Auth initiation failed");
  }
  const data = await res.json();
  if (data.session_token) storeSessionToken(data.session_token);
  return data;
}

export async function getAuthStatus(email: string): Promise<{
  connected: boolean;
  gmail_connected: boolean;
  calendar_connected: boolean;
  email?: string;
  session_token?: string;
}> {
  const res = await fetch(
    `${API_URL}/api/auth/status/${encodeURIComponent(email)}`
  );
  if (!res.ok)
    return { connected: false, gmail_connected: false, calendar_connected: false };
  const data = await res.json();
  if (data.session_token) storeSessionToken(data.session_token);
  return data;
}

export async function logout(email: string): Promise<void> {
  await fetch(`${API_URL}/api/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  clearSessionToken();
}

// ---------- Chat (SSE streaming) ----------

export async function* streamMessage(
  email: string,
  message: string,
  agentType: AgentType = "gmail"
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API_URL}/api/chat/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      message,
      agent_type: agentType,
      session_token: getStoredToken(),
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Chat request failed");
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith(SSE_DATA_PREFIX)) {
        try {
          yield JSON.parse(line.slice(SSE_DATA_PREFIX.length)) as SSEEvent;
        } catch {
          // malformed event — skip
        }
      }
    }
  }
}

// ---------- Greeting ----------

export async function getGreeting(
  email: string
): Promise<{ greeting: string; name: string | null }> {
  const res = await fetch(
    `${API_URL}/api/agents/greeting/${encodeURIComponent(email)}`
  );
  if (!res.ok) throw new Error("Greeting fetch failed");
  return res.json();
}

// ---------- Email Summarizer ----------

export async function triggerEmailSummarizer(
  email: string
): Promise<{ status: "queued" | "skipped" | "disabled" }> {
  const res = await fetch(`${API_URL}/api/agents/email-summarizer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) return { status: "disabled" };
  return res.json();
}

// ---------- WhatsApp notifications ----------

export async function getWhatsAppSettings(email: string): Promise<{
  ok: boolean;
  whatsapp_number: string;
  enabled: boolean;
  sandbox_keyword: string;
}> {
  const res = await fetch(
    `${API_URL}/api/notifications/whatsapp/${encodeURIComponent(email)}`
  );
  if (!res.ok) return { ok: false, whatsapp_number: "", enabled: false, sandbox_keyword: "" };
  return res.json();
}

export async function saveWhatsAppSettings(
  email: string,
  whatsappNumber: string,
  enabled: boolean
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${API_URL}/api/notifications/whatsapp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      whatsapp_number: whatsappNumber,
      enabled,
      session_token: getStoredToken(),
    }),
  });
  return res.json();
}

export async function sendTestWhatsApp(
  email: string,
  whatsappNumber: string
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${API_URL}/api/notifications/whatsapp/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      whatsapp_number: whatsappNumber,
      enabled: true,
      session_token: getStoredToken(),
    }),
  });
  const data = await res.json();
  if (!res.ok) return { ok: false, error: data.detail ?? "Failed" };
  return data;
}

// ---------- Settings ----------

export interface SettingItem {
  key: string;
  label: string;
  sensitive: boolean;
  value: string;
}

export async function getSettings(): Promise<SettingItem[]> {
  const res = await fetch(`${API_URL}/api/settings`);
  if (!res.ok) throw new Error("Failed to load settings");
  const data = await res.json();
  return data.settings;
}

export async function updateSettings(
  updates: Record<string, string>
): Promise<{ updated: string[] }> {
  const res = await fetch(`${API_URL}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to save settings");
  }
  return res.json();
}

// ---------- Conversation ----------

export async function clearMessages(
  email: string,
  agentType?: AgentType
): Promise<void> {
  await fetch(`${API_URL}/api/chat/clear`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      agent_type: agentType ?? null,
      session_token: getStoredToken(),
    }),
  });
}

// ---------- Trigger subscription helpers ----------

export async function subscribeTrigger(
  email: string,
  triggerName: string,
  config?: Record<string, unknown>
): Promise<{ ok: boolean; trigger_subscription_id?: string; error?: string }> {
  const res = await fetch(`${API_URL}/api/triggers/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      trigger_name: triggerName,
      config,
      session_token: getStoredToken(),
    }),
  });
  return res.json();
}

export async function unsubscribeTrigger(
  email: string,
  subscriptionId: string
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${API_URL}/api/triggers/unsubscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      trigger_subscription_id: subscriptionId,
      session_token: getStoredToken(),
    }),
  });
  return res.json();
}

// ---------- Trigger SSE stream URL (for EventSource) ----------

export function triggerStreamUrl(email: string): string {
  const token = getStoredToken();
  return `${API_URL}/api/triggers/stream/${encodeURIComponent(email)}?token=${encodeURIComponent(token)}`;
}
