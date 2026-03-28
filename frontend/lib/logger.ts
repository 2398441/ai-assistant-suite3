/**
 * Client-side error logger.
 *
 * Ships browser errors to the backend POST /api/log/error endpoint,
 * which appends them to the unified logs/app.log file.
 *
 * To disable: comment out the logClientError() calls in layout.tsx.
 * This file can remain — it will simply never be invoked.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Send a client-side error to the backend log endpoint.
 * Fire-and-forget — failures are silently ignored to avoid error loops.
 *
 * @param error   The error object or message string
 * @param context A short label identifying where the error came from
 *                e.g. "window.onerror", "unhandledrejection", "ChatWindow"
 */
export function logClientError(error: unknown, context?: string): void {
  const message =
    error instanceof Error
      ? `${error.name}: ${error.message}`
      : String(error);

  // Fire-and-forget — do not await, do not surface failures to the user
  fetch(`${API_BASE}/api/log/error`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: "FRONTEND", context: context ?? "", message }),
  }).catch(() => {
    // Intentionally swallowed — logging must never cause further errors
  });
}
