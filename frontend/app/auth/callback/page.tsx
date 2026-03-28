"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getAuthStatus, initiateAuth } from "@/lib/api";
import { Spinner, CloseIcon } from "@/components/ui/icons";
import {
  AUTH_POLL_MAX_ATTEMPTS,
  AUTH_POLL_INTERVAL_MS,
  AUTH_POLL_RETRY_MS,
  AUTH_REDIRECT_DELAY_MS,
  STORAGE_KEY_USER_EMAIL,
  STORAGE_KEY_PENDING_EMAIL,
} from "@/lib/constants";

/**
 * After Google OAuth, Composio redirects the user here.
 *
 * Sequential OAuth flow:
 *   1. Gmail OAuth completes → we land here.
 *   2. Poll /api/auth/status until gmail_connected=true.
 *   3. If calendar_connected=false, call /api/auth/initiate with agent_type="calendar"
 *      and redirect to the Calendar OAuth URL.
 *   4. Calendar OAuth completes → we land here again.
 *   5. Poll until both gmail_connected AND calendar_connected → go to chat.
 */
export default function AuthCallback() {
  const router = useRouter();
  const [status, setStatus] = useState("Completing sign-in…");
  const [attempts, setAttempts] = useState(0);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const email =
      params.get("email") ||
      localStorage.getItem(STORAGE_KEY_PENDING_EMAIL) ||
      localStorage.getItem(STORAGE_KEY_USER_EMAIL);

    if (!email) {
      router.replace("/");
      return;
    }

    let cancelled = false;

    async function initiateCalendarAuth() {
      const callbackUrl = `${window.location.origin}/auth/callback`;
      try {
        const result = await initiateAuth(email!, callbackUrl, "calendar");
        if (cancelled) return;
        if (result.connected) {
          // Calendar already connected — go straight to chat
          finish();
        } else if (result.auth_url) {
          setStatus("Connecting Google Calendar…");
          window.location.href = result.auth_url;
        } else {
          finish();
        }
      } catch {
        if (!cancelled) finish();
      }
    }

    function finish() {
      localStorage.setItem(STORAGE_KEY_USER_EMAIL, email!);
      localStorage.removeItem(STORAGE_KEY_PENDING_EMAIL);
      setStatus("All accounts connected! Redirecting…");
      setTimeout(
        () => router.replace(`/?email=${encodeURIComponent(email!)}`),
        AUTH_REDIRECT_DELAY_MS
      );
    }

    async function poll() {
      try {
        const result = await getAuthStatus(email!);
        if (cancelled) return;

        if (result.gmail_connected && result.calendar_connected) {
          finish();
          return;
        }

        if (result.gmail_connected && !result.calendar_connected) {
          setStatus("Gmail connected. Connecting Google Calendar…");
          await initiateCalendarAuth();
          return;
        }

        setAttempts((a) => {
          const next = a + 1;
          if (next >= AUTH_POLL_MAX_ATTEMPTS) {
            setStatus("Connection timed out. Please try again.");
            return next;
          }
          setStatus(
            result.gmail_connected
              ? "Waiting for Calendar connection…"
              : "Waiting for Gmail connection…"
          );
          setTimeout(poll, AUTH_POLL_INTERVAL_MS);
          return next;
        });
      } catch {
        if (!cancelled) setTimeout(poll, AUTH_POLL_RETRY_MS);
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const timedOut = attempts >= AUTH_POLL_MAX_ATTEMPTS;

  return (
    <div className="h-full flex flex-col items-center justify-center gap-4 text-center px-4">
      <div className="w-14 h-14 rounded-2xl bg-indigo-600 flex items-center justify-center shadow-lg">
        {timedOut ? (
          <CloseIcon className="w-7 h-7 text-white" />
        ) : (
          <Spinner className="w-7 h-7 text-white animate-spin" />
        )}
      </div>

      <div>
        <h1 className="text-lg font-semibold text-gray-800">
          {timedOut ? "Connection timed out" : "Connecting your accounts"}
        </h1>
        <p className="text-sm text-gray-500 mt-1">{status}</p>
      </div>

      {timedOut && (
        <button
          onClick={() => router.replace("/")}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          Return home
        </button>
      )}
    </div>
  );
}
