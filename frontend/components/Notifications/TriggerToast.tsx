"use client";

import { useEffect, useRef, useState } from "react";
import { NotificationItem } from "@/lib/types";
import { Spinner, ChevronIcon, CloseIcon, CheckIcon, SendIcon, BellIcon } from "@/components/ui/icons";
import {
  TOAST_SLIDE_OUT_MS,
  TOAST_FROM_PREVIEW_CHARS,
  TOAST_SUBJECT_PREVIEW_CHARS,
  TOAST_ERROR_PREVIEW_CHARS,
  TRIGGER_PREFIX_GMAIL,
  TRIGGER_PREFIX_GOOGLECAL,
  GMAIL_SEARCH_BASE_URL,
  OUTLOOK_DRAFT_BASE_URL,
  OUTLOOK_DRAFTS_URL,
  OUTLOOK_M365_DRAFT_BASE_URL,
  OUTLOOK_M365_DRAFTS_URL,
} from "@/lib/constants";

interface Props {
  /** The notification to display. Set to null only when explicitly dismissed (X). */
  notification: NotificationItem | null;
  onDismiss: () => void;
}

// ── Visual config per notification flavour ─────────────────────────────────

function getStyle(n: NotificationItem) {
  if (n.is_error) return {
    gradient: "from-red-500 to-rose-600",
    badge:    "bg-red-50 text-red-700",
    hint:     "text-red-400",
    dot:      "bg-red-400",
  };
  if (n.type === "agent_complete") return {
    gradient: "from-indigo-500 to-violet-600",
    badge:    "bg-indigo-50 text-indigo-700",
    hint:     "text-indigo-400",
    dot:      "bg-indigo-500",
  };
  if (n.trigger_name?.startsWith(TRIGGER_PREFIX_GMAIL)) return {
    gradient: "from-rose-500 to-red-600",
    badge:    "bg-rose-50 text-rose-700",
    hint:     "text-rose-400",
    dot:      "bg-rose-500",
  };
  return {
    gradient: "from-blue-500 to-cyan-600",
    badge:    "bg-blue-50 text-blue-700",
    hint:     "text-blue-400",
    dot:      "bg-blue-500",
  };
}

function getSource(n: NotificationItem): string {
  if (n.type === "agent_complete")            return "AI Assistant";
  if (n.trigger_name?.startsWith(TRIGGER_PREFIX_GMAIL))   return "Gmail";
  if (n.trigger_name?.startsWith(TRIGGER_PREFIX_GOOGLECAL)) return "Google Calendar";
  return "Notification";
}

function getStats(n: NotificationItem): { icon: string; label: string; value: string; href?: string }[] {
  if (n.type === "agent_complete") {
    if (n.is_processing) return [];  // no stats while processing
    const s: { icon: string; label: string; value: string; href?: string }[] = [];
    if (n.email_count)   s.push({ icon: "📧", label: "Scanned", value: `${n.email_count} email${n.email_count !== 1 ? "s" : ""}` });
    if (n.timestamp)     s.push({ icon: "🕐", label: "At",      value: n.timestamp });
    if (n.draft_subject) {
      let href: string;
      if (n.provider === "Outlook") {
        href = n.draft_id
          ? `${OUTLOOK_DRAFT_BASE_URL}/${encodeURIComponent(n.draft_id)}`
          : OUTLOOK_DRAFTS_URL;
      } else if (n.provider === "Outlook365") {
        href = n.draft_id
          ? `${OUTLOOK_M365_DRAFT_BASE_URL}/${encodeURIComponent(n.draft_id)}`
          : OUTLOOK_M365_DRAFTS_URL;
      } else {
        href = `${GMAIL_SEARCH_BASE_URL}/${encodeURIComponent(n.draft_subject)}`;
      }
      s.push({
        icon: "📎", label: "Draft",
        value: (n.provider === "Outlook" || n.provider === "Outlook365") ? "Open in Outlook →" : "Open in Gmail →",
        href,
      });
    }
    return s;
  }
  const p = n.payload ?? {};
  const s: { icon: string; label: string; value: string }[] = [];
  if (n.trigger_name?.startsWith(TRIGGER_PREFIX_GMAIL)) {
    if (p.from)    s.push({ icon: "👤", label: "From",    value: String(p.from).slice(0, TOAST_FROM_PREVIEW_CHARS) });
    if (p.subject) s.push({ icon: "📌", label: "Subject", value: String(p.subject).slice(0, TOAST_SUBJECT_PREVIEW_CHARS) });
  } else {
    const title    = (p.summary ?? p.title) as string | undefined;
    const start    = p.start as Record<string, string> | string | undefined;
    const startStr = typeof start === "object" ? (start.dateTime ?? start.date) : start;
    if (title)    s.push({ icon: "📅", label: "Event", value: String(title).slice(0, TOAST_SUBJECT_PREVIEW_CHARS) });
    if (startStr) {
      try {
        s.push({ icon: "🕐", label: "When", value: new Date(startStr).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) });
      } catch { /* ignore */ }
    }
  }
  return s;
}

function getHint(n: NotificationItem): string {
  if (n.is_error)                  return "See bell for error details";
  if (n.is_processing)             return "Working in background…";
  if (n.type === "agent_complete") return "Open bell to view action items →";
  return "Open bell to view details →";
}

// ── Component ──────────────────────────────────────────────────────────────

export function TriggerToast({ notification, onDismiss }: Props) {
  // slideIn: controls the outer max-h animation (slide open on arrival)
  const [slideIn, setSlideIn]     = useState(false);
  const [mounted, setMounted]     = useState(false);
  // bodyOpen: user-controlled collapse — body visible vs header-only
  const [bodyOpen, setBodyOpen]   = useState(true);
  const prevIdRef = useRef<string | null>(null);

  // Slide in when a new notification arrives; reset body to open
  useEffect(() => {
    if (notification && notification.id !== prevIdRef.current) {
      prevIdRef.current = notification.id;
      setMounted(true);
      setBodyOpen(true);
      const raf = requestAnimationFrame(() => setSlideIn(true));
      return () => cancelAnimationFrame(raf);
    }
  }, [notification]);

  // Slide out + unmount only when notification is explicitly cleared (X button)
  useEffect(() => {
    if (!notification && mounted) {
      setSlideIn(false);
      const t = setTimeout(() => setMounted(false), TOAST_SLIDE_OUT_MS);
      return () => clearTimeout(t);
    }
  }, [notification, mounted]);

  if (!mounted || !notification) return null;

  const style = getStyle(notification);
  const stats = getStats(notification);

  return (
    <div
      role="status"
      aria-live="polite"
      className={`overflow-hidden transition-all duration-350 ease-out rounded-xl shadow-xl border border-gray-200
        ${slideIn ? "max-h-72 opacity-100" : "max-h-0 opacity-0"}`}
    >
      {/* ── Gradient header ─────────────────────────────────────────────── */}
      <div className={`relative bg-gradient-to-r ${style.gradient} px-3 py-2.5 overflow-hidden`}>
        {/* Animated shimmer sweep when processing */}
        {notification.is_processing && (
          <div
            className="absolute inset-0 -translate-x-full animate-[shimmer_1.8s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-white/15 to-transparent pointer-events-none"
          />
        )}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2 min-w-0">
            {/* Icon — spinner when processing, emoji otherwise */}
            <span className="flex-shrink-0 w-7 h-7 rounded-full bg-white/20 flex items-center justify-center text-sm leading-none">
              {notification.is_processing ? (
                <svg className="w-4 h-4 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-30" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
              ) : (
                notification.icon
              )}
            </span>
            <div className="min-w-0 pt-0.5">
              <p className="text-white font-semibold text-[11px] leading-tight truncate">
                {notification.title}
              </p>
              <div className="flex items-center gap-1 mt-0.5">
                {notification.is_processing && (
                  <span className="w-1 h-1 rounded-full bg-white animate-ping inline-block" />
                )}
                <p className="text-white/65 text-[9px]">
                  {notification.is_processing ? "Processing…" : getSource(notification)}
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1 flex-shrink-0">
            {/* Collapse / expand toggle */}
            <button
              onClick={() => setBodyOpen((v) => !v)}
              className="w-5 h-5 rounded-full bg-white/20 hover:bg-white/35 flex items-center justify-center transition-colors"
              aria-label={bodyOpen ? "Collapse" : "Expand"}
            >
              <ChevronIcon className={`w-2.5 h-2.5 text-white transition-transform duration-200 ${bodyOpen ? "" : "rotate-180"}`} strokeWidth={2.5} />
            </button>

            {/* Dismiss (× — only way to remove the toast) */}
            <button
              onClick={onDismiss}
              className="w-5 h-5 rounded-full bg-white/20 hover:bg-white/35 flex items-center justify-center transition-colors"
              aria-label="Dismiss"
            >
              <CloseIcon className="w-2.5 h-2.5 text-white" strokeWidth={2.5} />
            </button>
          </div>
        </div>
      </div>

      {/* ── White body — hidden when collapsed ──────────────────────────── */}
      <div className={`overflow-hidden transition-all duration-250 ease-in-out ${bodyOpen ? "max-h-48" : "max-h-0"}`}>
        <div className="bg-white px-3 py-2.5 space-y-2">

          {/* Processing spinner */}
          {notification.is_processing && (
            <div className="flex items-center gap-2 py-1">
              <Spinner className="w-3.5 h-3.5 text-indigo-500 animate-spin flex-shrink-0" />
              <span className="text-[10px] text-gray-500">
                Analysing {notification.email_count ? `${notification.email_count} email${notification.email_count !== 1 ? "s" : ""}` : "emails"} — results will appear in the bell
              </span>
            </div>
          )}

          {/* Stat pills */}
          {!notification.is_processing && stats.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {stats.map((s) => {
                const inner = (
                  <>
                    <span className="leading-none">{s.icon}</span>
                    <span className="text-gray-400 font-normal">{s.label}:</span>
                    <span>{s.value}</span>
                  </>
                );
                return s.href ? (
                  <a
                    key={s.label}
                    href={s.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className={`flex items-center gap-1 px-2 py-1 rounded-md ${style.badge} text-[10px] font-medium hover:opacity-80 transition-opacity`}
                  >
                    {inner}
                  </a>
                ) : (
                  <div key={s.label} className={`flex items-center gap-1 px-2 py-1 rounded-md ${style.badge} text-[10px] font-medium`}>
                    {inner}
                  </div>
                );
              })}
            </div>
          )}

          {/* Error message */}
          {notification.is_error && notification.body && (
            <p className="text-[10px] text-red-600 bg-red-50 rounded px-2 py-1.5 leading-relaxed">
              {notification.body.slice(0, TOAST_ERROR_PREVIEW_CHARS)}
            </p>
          )}

          {/* Hint footer */}
          <div className="flex items-center justify-between pt-1 border-t border-gray-100">
            <div className="flex items-center gap-1">
              <span className={`w-1.5 h-1.5 rounded-full ${style.dot} animate-pulse flex-shrink-0`} />
              <span className={`text-[9px] font-medium ${style.hint}`}>
                {getHint(notification)}
              </span>
            </div>
            <BellIcon className={`w-3 h-3 ${style.hint} flex-shrink-0`} />
          </div>
        </div>
      </div>
    </div>
  );
}
