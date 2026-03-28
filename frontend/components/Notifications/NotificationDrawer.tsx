"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { NotificationItem } from "@/lib/types";
import { FormattedContent } from "@/components/ui/MarkdownContent";
import { Spinner, BellIcon, CloseIcon, ChevronIcon, ClockIcon } from "@/components/ui/icons";
import {
  ELAPSED_TIME_TICK_MS,
  BELL_RING_DURATION_MS,
  NOTIFICATION_BODY_PREVIEW_CHARS,
  NOTIFICATION_SNIPPET_PREVIEW_CHARS,
  TRIGGER_PREFIX_GMAIL,
  GMAIL_SEARCH_BASE_URL,
  UNREAD_BADGE_MAX,
  UNREAD_BADGE_DISPLAY,
  KEY_ESCAPE,
} from "@/lib/constants";

interface Props {
  notifications: NotificationItem[];
  onMarkAllRead: () => void;
  onMarkRead: (id: string) => void;
  onClear: () => void;
  /** Called when the drawer is opened — used to dismiss any active toast */
  onOpen?: () => void;
}

export function NotificationDrawer({ notifications, onMarkAllRead, onMarkRead, onClear, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [bellRinging, setBellRinging] = useState(false);
  const prevUnreadRef = useRef(0);

  const unread = notifications.filter((n) => !n.read).length;
  const isProcessing = notifications.some((n) => n.is_processing);
  const processingItem = notifications.find((n) => n.is_processing);

  const [elapsed, setElapsed]       = useState(0);
  const [showTimer, setShowTimer]   = useState(false);
  const timerBtnRef                 = useRef<HTMLButtonElement>(null);

  // Tick elapsed seconds while a processing item is live
  useEffect(() => {
    if (!isProcessing || !processingItem) { setElapsed(0); return; }
    const startedAt = processingItem.createdAt;
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    const id = setInterval(tick, ELAPSED_TIME_TICK_MS);
    return () => clearInterval(id);
  }, [isProcessing, processingItem]);

  // Close timer popover on outside click
  useEffect(() => {
    if (!showTimer) return;
    function handler(e: MouseEvent) {
      if (timerBtnRef.current && !timerBtnRef.current.contains(e.target as Node))
        setShowTimer(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showTimer]);

  function formatElapsed(secs: number): string {
    if (secs < 60) return `${secs}s`;
    return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  }

  // Ring the bell whenever the unread count goes up
  useEffect(() => {
    if (unread > prevUnreadRef.current) {
      setBellRinging(true);
      const t = setTimeout(() => setBellRinging(false), BELL_RING_DURATION_MS);
      prevUnreadRef.current = unread;
      return () => clearTimeout(t);
    }
    prevUnreadRef.current = unread;
  }, [unread]);

  // Mark all read when drawer opens
  useEffect(() => {
    if (open) onMarkAllRead();
  }, [open, onMarkAllRead]);

  // Escape to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === KEY_ESCAPE) setOpen(false); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  // Prevent body scroll while drawer is open
  useEffect(() => {
    document.body.classList.toggle("overflow-hidden", open);
    return () => { document.body.classList.remove("overflow-hidden"); };
  }, [open]);

  const handleToggle = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
    onMarkRead(id);
  }, [onMarkRead]);

  return (
    <>
      {/* ── Bell button ──────────────────────────────────────────────────── */}
      <button
        onClick={() => { setOpen(true); onOpen?.(); }}
        className={`relative p-1.5 rounded-lg transition-colors ${
          isProcessing
            ? "text-indigo-600 bg-indigo-50 hover:bg-indigo-100"
            : bellRinging
              ? "text-indigo-600 bg-indigo-50 hover:bg-indigo-100"
              : "text-gray-400 hover:text-gray-600 hover:bg-gray-100"
        }`}
        title="Notifications"
        aria-label="Open notifications"
      >
        {/* Pulsing ring behind the bell while processing */}
        {isProcessing && (
          <span className="absolute inset-0 rounded-lg bg-indigo-400 opacity-20 animate-ping" />
        )}
        <BellIcon className={`w-4 h-4 transition-transform ${bellRinging ? "animate-[ring_0.5s_ease-in-out_4] [transform-origin:50%_0%]" : ""}`} />
        {unread > 0 && (
          <span className={`absolute -top-0.5 -right-0.5 flex items-center justify-center w-4 h-4 text-[9px] font-bold text-white rounded-full transition-all duration-300 ${
            isProcessing ? "bg-indigo-500 animate-pulse" : bellRinging ? "bg-indigo-500 scale-125" : "bg-red-500 scale-100"
          }`}>
            {unread > UNREAD_BADGE_MAX ? UNREAD_BADGE_DISPLAY : unread}
          </span>
        )}
      </button>

      {/* ── Backdrop ─────────────────────────────────────────────────────── */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px]"
          onClick={() => setOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── Drawer panel ─────────────────────────────────────────────────── */}
      <div
        role="dialog"
        aria-label="Notifications"
        className={`fixed top-0 right-0 h-full w-96 max-w-full bg-white shadow-2xl z-50 flex flex-col transition-transform duration-300 ease-in-out ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Header */}
        <div className={`relative shrink-0 transition-colors ${isProcessing ? "bg-indigo-50/60" : ""}`}>
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2">
              {isProcessing && (
                <Spinner className="w-3.5 h-3.5 text-indigo-500 animate-spin flex-shrink-0" />
              )}
              <h2 className="font-semibold text-gray-800 text-sm">Notifications</h2>
              {isProcessing ? (
                <span className="flex items-center gap-1 text-[10px] text-indigo-600 bg-indigo-100 px-1.5 py-0.5 rounded-full font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-ping inline-block" />
                  Processing…
                </span>
              ) : notifications.length > 0 && (
                <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full font-medium">
                  {notifications.length}
                </span>
              )}
            </div>

            <div className="flex items-center gap-1">
              {/* Timer icon — only while processing */}
              {isProcessing && (
                <div className="relative">
                  <button
                    ref={timerBtnRef}
                    onClick={() => setShowTimer((v) => !v)}
                    className="p-1.5 text-indigo-400 hover:text-indigo-600 hover:bg-indigo-100 rounded-lg transition-colors"
                    title="Show elapsed time"
                    aria-label="Show elapsed time"
                  >
                    <ClockIcon className="w-3.5 h-3.5" />
                  </button>
                  {showTimer && (
                    <div className="absolute right-0 top-full mt-1 z-50 bg-gray-900 text-white text-[11px] font-mono px-2.5 py-1.5 rounded-lg shadow-lg whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <Spinner className="w-3 h-3 text-indigo-300 animate-spin flex-shrink-0" />
                        <span className="text-gray-300">Processing for</span>
                        <span className="text-white font-bold">{formatElapsed(elapsed)}</span>
                      </div>
                      {/* Caret */}
                      <div className="absolute -top-1 right-3 w-2 h-2 bg-gray-900 rotate-45" />
                    </div>
                  )}
                </div>
              )}

              {notifications.length > 0 && (
                <button
                  onClick={() => { onClear(); setExpandedId(null); }}
                  className="text-xs text-gray-400 hover:text-red-500 px-2 py-1 rounded hover:bg-red-50 transition-colors"
                >
                  Clear all
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                aria-label="Close notifications"
              >
                <CloseIcon className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Indeterminate progress bar — bottom of header */}
          {isProcessing ? (
            <div className="h-0.5 bg-indigo-100 overflow-hidden">
              <div className="h-full w-1/3 bg-indigo-400 animate-indeterminate" />
            </div>
          ) : (
            <div className="h-px bg-gray-200" />
          )}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {notifications.length === 0 ? (
            <EmptyState />
          ) : (
            <ul className="divide-y divide-gray-100">
              {notifications.map((n) => (
                <NotificationRow
                  key={n.id}
                  item={n}
                  expanded={expandedId === n.id}
                  onToggle={() => handleToggle(n.id)}
                />
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400 py-16">
      <BellIcon className="w-12 h-12 opacity-20" strokeWidth={1.5} />
      <p className="text-sm">No notifications yet</p>
    </div>
  );
}

// ── Notification row (accordion) ──────────────────────────────────────────────

interface RowProps {
  item: NotificationItem;
  expanded: boolean;
  onToggle: () => void;
}

function NotificationRow({ item, expanded, onToggle }: RowProps) {
  return (
    <li className={`transition-colors ${!item.read && !expanded ? "bg-blue-50/40" : ""}`}>
      <button
        className="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors flex items-start gap-3"
        onClick={onToggle}
      >
        {/* Icon — spinning when processing */}
        {item.is_processing ? (
          <Spinner className="w-5 h-5 text-indigo-400 animate-spin flex-shrink-0 mt-0.5" />
        ) : (
          <span className="text-lg flex-shrink-0 mt-0.5 leading-none">{item.icon}</span>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className={`text-xs font-semibold truncate ${item.is_error ? "text-red-700" : item.is_processing ? "text-indigo-600" : "text-gray-800"}`}>
              {item.title}
            </p>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {!item.read && (
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full flex-shrink-0" />
              )}
              <span className="text-[10px] text-gray-400 whitespace-nowrap">{item.timestamp}</span>
            </div>
          </div>
          {!expanded && (
            <p className="text-[11px] text-gray-400 mt-0.5 truncate">{getPreview(item)}</p>
          )}
        </div>
        <ChevronIcon className={`w-3.5 h-3.5 text-gray-300 flex-shrink-0 mt-1 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-50">
          {item.type === "agent_complete"
            ? <AgentCompleteDetail item={item} />
            : <TriggerDetail item={item} />
          }
        </div>
      )}
    </li>
  );
}

// ── Expanded: agent_complete ──────────────────────────────────────────────────

function AgentCompleteDetail({ item }: { item: NotificationItem }) {
  if (item.is_processing) {
    return (
      <div className="pt-3 flex items-start gap-2.5">
        <Spinner className="w-4 h-4 text-indigo-400 animate-spin flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="text-xs font-medium text-indigo-600">Analysing emails in background…</p>
          {!!item.email_count && (
            <p className="text-[11px] text-gray-400">
              {item.email_count} email{item.email_count !== 1 ? "s" : ""} queued for processing
            </p>
          )}
          <p className="text-[11px] text-gray-400">Results will replace this entry when ready.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="pt-3 space-y-3">
      {item.body && (
        <div className="text-xs">
          <FormattedContent content={item.body} />
        </div>
      )}
      <div className="space-y-2 border-t border-gray-100 pt-3">
        {item.timestamp    && <MetaRow icon="🕐" label="Scanned at"     value={item.timestamp} />}
        {!!item.email_count && <MetaRow icon="📊" label="Emails scanned" value={String(item.email_count)} />}
        {item.draft_subject && (
          <div className="flex items-start gap-1.5 text-[11px]">
            <span className="flex-shrink-0">📎</span>
            <span>
              <span className="text-gray-700 font-medium">Draft saved: </span>
              <a
                href={`${GMAIL_SEARCH_BASE_URL}/${encodeURIComponent(item.draft_subject)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-600 hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                Open in Gmail →
              </a>
            </span>
          </div>
        )}
        {item.mode          && <MetaRow icon="⚙️" label="Mode"      value={item.mode === "smart" ? "smart (deduplication on)" : item.mode} />}
        {item.inclusion_rule && <MetaRow icon="✅" label="Included"  value={item.inclusion_rule} />}
        {item.exclusion_rule && <MetaRow icon="🚫" label="Excluded"  value={item.exclusion_rule} />}
      </div>
    </div>
  );
}

// ── Expanded: trigger ─────────────────────────────────────────────────────────

function TriggerDetail({ item }: { item: NotificationItem }) {
  const rows = buildTriggerRows(item);
  return (
    <div className="pt-3 space-y-2">
      {rows.length === 0
        ? <p className="text-[11px] text-gray-400 italic">No additional details.</p>
        : rows.map((row, i) => <MetaRow key={i} icon={row.icon} label={row.label} value={row.value} />)
      }
    </div>
  );
}

// ── Shared MetaRow ────────────────────────────────────────────────────────────

function MetaRow({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="flex items-start gap-1.5 text-[11px]">
      <span className="flex-shrink-0">{icon}</span>
      <span>
        <span className="text-gray-700 font-medium">{label}: </span>
        <span className="text-gray-500">{value}</span>
      </span>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getPreview(item: NotificationItem): string {
  if (item.type === "agent_complete") {
    if (item.is_processing) return item.email_count
      ? `Scanning ${item.email_count} email${item.email_count !== 1 ? "s" : ""}…`
      : "Scanning your inbox…";
    if (item.is_error) return item.body?.slice(0, NOTIFICATION_BODY_PREVIEW_CHARS) ?? "";
    if (item.email_count) return `${item.email_count} email${item.email_count !== 1 ? "s" : ""} scanned`;
    return "Tap to view action items";
  }
  const p = item.payload ?? {};
  if (item.trigger_name?.startsWith(TRIGGER_PREFIX_GMAIL)) {
    return [p.from, p.subject].filter(Boolean).map(String).join(" · ");
  }
  const title = ((p.summary ?? p.title) as string | undefined) ?? "";
  const start  = p.start as Record<string, string> | string | undefined;
  const startStr = typeof start === "object" ? (start.dateTime ?? start.date) : start;
  return [title, startStr ? formatDate(startStr) : ""].filter(Boolean).join(" · ");
}

function buildTriggerRows(item: NotificationItem): { icon: string; label: string; value: string }[] {
  const p    = item.payload ?? {};
  const rows: { icon: string; label: string; value: string }[] = [];

  if (item.trigger_name?.startsWith(TRIGGER_PREFIX_GMAIL)) {
    if (p.from)    rows.push({ icon: "👤", label: "From",    value: String(p.from) });
    if (p.subject) rows.push({ icon: "📌", label: "Subject", value: String(p.subject) });
    if (p.snippet) rows.push({ icon: "✉️", label: "Preview", value: String(p.snippet).slice(0, NOTIFICATION_SNIPPET_PREVIEW_CHARS) });
  } else {
    const title    = (p.summary ?? p.title) as string | undefined;
    const start    = p.start as Record<string, string> | string | undefined;
    const startStr = typeof start === "object" ? (start.dateTime ?? start.date) : start;
    const attendee = p.attendee as { email?: string; displayName?: string } | undefined;
    const mins     = p.minutes_until_start as number | undefined;
    const status   = (p.response_status ?? p.responseStatus) as string | undefined;

    if (title)    rows.push({ icon: "📅", label: "Event",     value: title });
    if (startStr) rows.push({ icon: "🕐", label: "When",      value: formatDate(startStr) });
    if (attendee) rows.push({ icon: "👤", label: "Attendee",  value: attendee.displayName ?? attendee.email ?? "" });
    if (status)   rows.push({ icon: "📝", label: "Response",  value: status });
    if (mins != null) rows.push({ icon: "⏱️", label: "Starts in", value: `${mins} min` });
  }
  return rows;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
