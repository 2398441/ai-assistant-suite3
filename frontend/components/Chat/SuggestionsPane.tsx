"use client";

import { useState, useEffect, useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import { AgentType, NotificationItem } from "@/lib/types";
import { PlusIcon, PencilIcon, TrashIcon, ChevronIcon } from "@/components/ui/icons";
import { FOCUS_DELAY_MS, QUICK_ACTION_LABEL_MAX, QUICK_ACTION_TEXT_MAX, KEY_ENTER, KEY_ESCAPE } from "@/lib/constants";
import { ICON_PALETTE, autoIcon } from "@/lib/icons";
import { AGENT_META } from "@/lib/agents";
import { UI } from "@/lib/styles";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Suggestion {
  id: string;
  icon: string;
  label: string;
  text: string;
}

interface SuggestionsPaneProps {
  onSuggestion: (text: string, agentType: AgentType, label: string, isDefault: boolean) => void;
  activeAgent: AgentType;
  onAgentChange: (agent: AgentType) => void;
  disabled?: boolean;
  /** Used only for the status dot / "1 new" badge — toast renders separately in page.tsx */
  notification?: NotificationItem | null;
}

// ── Defaults — icons derived automatically via autoIcon() ─────────────────────
// To add a new suggestion: just supply id, label, text. Icon is auto-derived.
// To change an icon pattern: update ICON_RULES in @/lib/icons.

const GMAIL_DEFAULTS: Suggestion[] = [
  { id: "g0", label: "My Gmail Features",  text: "Provide consice summary of the tools I have acces to including custom ones?" },
  { id: "g1", label: "Inbox Digest",        text: "Summarise my emails from the last 2 business days" },
  { id: "g2", label: "Awaiting Reply",      text: "Find emails where I haven't replied in over 3 business days" },
  { id: "g3", label: "Urgent & Flagged",    text: "Show emails marked urgent or flagged by my team" },
  { id: "g4", label: "Draft Follow-up",     text: "Draft a follow-up email for my most recent unanswered thread" },
  { id: "g5", label: "Sender Summary",      text: "Who has emailed me the most since last 3 business days and about what?" },
  { id: "g6", label: "Organise Inbox",      text: "Help me identify emails I can archive or label to clean up my inbox" },
  { id: "g7", label: "Deduplicate Drafts",  text: "Find all my Gmail drafts this week whose subject has ACTION-ITEMS . Compare their action-item tables and identify any duplicate entries (same sender + same required action). Consolidate everything into one updated draft that keeps only unique, highest-priority items — sorted 🔴 first — then delete the older redundant drafts. Show me a summary of what was merged and what was removed." },
].map(s => ({ ...s, icon: autoIcon(s.label, s.text) }));

const WORKSPACE_DEFAULTS: Suggestion[] = [
  { id: "w0", label: "Workspace Overview",                 text: "Provide consice summary of the tools I have acces to including custom ones?" },
  { id: "w1", label: "Schedule & Meet",                    text: "Schedule a meeting with a colleague, and perform necessary actions on conflicts." },
  { id: "w2", label: "Schedule & Email",                   text: "Find me a free 30-minute slot this week, schedule a meeting with a colleague, and email them the agenda." },
  { id: "w3", label: "Morning Brief",                      text: "Give me a combined morning briefing: scan all important emails (not just unread — read emails directly for completeness) from the last 2 business days and list today's calendar events." },
  { id: "w4", label: "Email from Invite",                  text: "Look at my most recent calendar invite and draft a confirmation email to all attendees with the meeting details." },
  { id: "w5", label: "Event from Email",                   text: "Find the most recent email about a meeting or event and create a calendar entry from the details." },
  { id: "w6", label: "Action Items",                       text: "Check my emails and calendar for today — pull out all action items and deadlines I need to be aware of." },
  { id: "w7", label: "Share Action Items - WhatsApp (via Twilio)", text: "Find my latest Gmail draft with ACTION-ITEMS in the subject. Show me the draft subject and the action items inside it. Then ask me: (1) which items I'd like to share — all or specific ones, and (2) who I want to send them to. Look up the recipient's WhatsApp or mobile number from my Google Contacts and send the selected items via WhatsApp." },
].map(s => ({ ...s, icon: autoIcon(s.label, s.text) }));

const CALENDAR_DEFAULTS: Suggestion[] = [
  { id: "c0", label: "My Calendar Features", text: "Provide consice summary of the tools I have acces to including custom ones?" },
  { id: "c1", label: "Today's Schedule",      text: "What events do I have scheduled for today?" },
  { id: "c2", label: "This Week's Meetings",  text: "Show me all my meetings for this week" },
  { id: "c3", label: "Find Free Slots",       text: "Find me a free 30-minute slot this week for a meeting" },
  { id: "c4", label: "Quick Event",           text: "Create a 30-minute team standup tomorrow morning at 9am" },
  { id: "c5", label: "Upcoming Deadlines",    text: "What are my upcoming calendar deadlines and reminders?" },
  { id: "c6", label: "Schedule Meeting",      text: "Schedule a 30-minute meeting with my team next week and send invites" },
].map(s => ({ ...s, icon: autoIcon(s.label, s.text) }));

// Stable keys — no version suffix needed. Merge logic (see AgentSection) ensures
// new defaults are appended automatically without a hard reload.
const STORAGE_KEYS: Record<AgentType, string> = {
  gmail:     "quick_actions_gmail",
  calendar:  "quick_actions_calendar",
  workspace: "quick_actions_workspace",
};

// ICON_PALETTE is imported from @/lib/icons
// Agent colours are imported from AGENT_META in @/lib/agents

// ── Component ─────────────────────────────────────────────────────────────────

export function SuggestionsPane({
  onSuggestion,
  activeAgent,
  onAgentChange,
  disabled,
  notification,
}: SuggestionsPaneProps) {
  return (
    <aside className="flex-1 min-h-0 bg-white flex flex-col overflow-hidden">

      {/* ── 1. Notifications status strip (pinned top) ───────────────── */}
      <NotificationsSection notification={notification ?? null} />

      {/* ── 2. Quick Actions ──────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">

        {/* Header label */}
        <div className="px-4 pt-3 pb-2 shrink-0">
          <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-widest">
            Quick Actions
          </p>
          <p className="text-[10px] text-gray-400 mt-0.5">Click to send · hover to edit</p>
        </div>

        {/* Scrollable area holding all agent cards */}
        <div className="flex-1 min-h-0 overflow-y-auto px-3 pb-3 flex flex-col gap-2">

          {/* ── Workspace Agent card ──────────────────────────────────── */}
          <AgentSection
            agentType="workspace"
            isActive={activeAgent === "workspace"}
            onActivate={() => onAgentChange("workspace")}
            onSuggestion={(text, label, isDefault) => onSuggestion(text, "workspace", label, isDefault)}
            disabled={!!disabled}
          />

          {/* ── Gmail Agent card ─────────────────────────────────────── */}
          <AgentSection
            agentType="gmail"
            isActive={activeAgent === "gmail"}
            onActivate={() => onAgentChange("gmail")}
            onSuggestion={(text, label, isDefault) => onSuggestion(text, "gmail", label, isDefault)}
            disabled={!!disabled}
          />

          {/* ── Calendar Agent card ───────────────────────────────────── */}
          <AgentSection
            agentType="calendar"
            isActive={activeAgent === "calendar"}
            onActivate={() => onAgentChange("calendar")}
            onSuggestion={(text, label, isDefault) => onSuggestion(text, "calendar", label, isDefault)}
            disabled={!!disabled}
          />

        </div>
      </div>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <div className="px-4 py-3 border-t border-gray-100 shrink-0">
        <p className="text-[10px] text-gray-300">Gmail &amp; Calendar Assistant</p>
      </div>
    </aside>
  );
}

// ── Notifications status strip ─────────────────────────────────────────────────
// Four-state intelligent progress widget — toast floats separately (see page.tsx).

const DOTS_STEP_MS = 500;

function NotificationsSection({ notification }: { notification: NotificationItem | null }) {
  const isProcessing = !!notification?.is_processing;
  const isError      = !!notification?.is_error;

  const [dots, setDots] = useState("");

  // Animate trailing dots while processing
  useEffect(() => {
    if (!isProcessing) { setDots(""); return; }
    const dotsId = setInterval(() => setDots((d) => (d.length >= 3 ? "" : d + "·")), DOTS_STEP_MS);
    return () => clearInterval(dotsId);
  }, [isProcessing]);

  // ── Idle ──────────────────────────────────────────────────────────────────
  if (!notification) {
    return (
      <div className="shrink-0 border-b border-gray-100 px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-gray-300 flex-shrink-0" />
          <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
            Notifications
          </span>
        </div>
        <span className="text-[9px] text-gray-300 italic">No new</span>
      </div>
    );
  }

  // ── Processing ────────────────────────────────────────────────────────────
  if (isProcessing) {
    return (
      <div className="shrink-0 border-b border-indigo-200 overflow-hidden">
        {/* Coloured header */}
        <div className="flex items-center justify-between px-3 py-1.5 bg-indigo-600">
          <div className="flex items-center gap-1.5">
            <svg className="w-3 h-3 text-white animate-spin flex-shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-30" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            <span className="text-[10px] font-bold text-white uppercase tracking-widest">Summarizer</span>
          </div>
          <span className="text-[9px] font-semibold text-indigo-200">active</span>
        </div>
        {/* Indeterminate scan bar */}
        <div className="relative h-1 bg-indigo-100 overflow-hidden">
          <div className="absolute inset-y-0 w-1/3 bg-indigo-500 rounded-full animate-indeterminate" />
        </div>
        {/* Real-time step label from backend */}
        <div className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50">
          <span className="text-[10px] text-indigo-700 font-medium">
            {notification.title}
            <span className="text-indigo-400 tracking-widest">{dots}</span>
          </span>
        </div>
      </div>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (isError) {
    return (
      <div className="shrink-0 border-b border-red-200">
        <div className="flex items-center justify-between px-3 py-1.5 bg-red-50">
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
            <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest">Notifications</span>
          </div>
          <span className="text-[9px] font-semibold text-red-600 bg-red-100 px-1.5 py-0.5 rounded-full border border-red-200">
            error
          </span>
        </div>
        <div className="flex items-center gap-1 px-3 pb-2 pt-0.5">
          <span className="text-[10px]">⚠️</span>
          <span className="text-[10px] text-red-600 truncate">{notification.title}</span>
        </div>
      </div>
    );
  }

  // ── Done ──────────────────────────────────────────────────────────────────
  return (
    <div className="shrink-0 border-b border-green-200">
      <div className="flex items-center justify-between px-3 py-1.5 bg-green-50">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse flex-shrink-0" />
          <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest">Notifications</span>
        </div>
        <span className="text-[9px] font-semibold text-green-700 bg-green-100 px-1.5 py-0.5 rounded-full border border-green-200">
          1 new
        </span>
      </div>
      <div className="flex items-center gap-1.5 px-3 pb-2 pt-0.5">
        <span className="text-[10px]">{notification.icon}</span>
        <span className="text-[10px] text-gray-600 truncate font-medium">{notification.title}</span>
      </div>
    </div>
  );
}

// ── AgentSection ──────────────────────────────────────────────────────────────

type EditMode = { kind: "edit"; id: string } | { kind: "add" } | null;

function AgentSection({
  agentType,
  isActive,
  onActivate,
  onSuggestion,
  disabled,
}: {
  agentType: AgentType;
  isActive: boolean;
  onActivate: () => void;
  onSuggestion: (text: string, label: string, isDefault: boolean) => void;
  disabled: boolean;
}) {
  const defaults = agentType === "gmail" ? GMAIL_DEFAULTS : agentType === "workspace" ? WORKSPACE_DEFAULTS : CALENDAR_DEFAULTS;
  const colors = AGENT_META[agentType].colors;

  const [suggestions, setSuggestions] = useState<Suggestion[]>(defaults);
  const [editMode, setEditMode] = useState<EditMode>(null);
  const [form, setForm] = useState({ icon: "💬", label: "", text: "" });
  const [showPicker, setShowPicker] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(agentType !== "workspace");
  const pickerRef = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLInputElement>(null);

  // Load from localStorage and merge in any new defaults not yet stored.
  // This means adding a new default in code auto-appears on next load without
  // requiring a hard reload or version key bump.
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEYS[agentType]);
      if (stored) {
        const parsed: Suggestion[] = JSON.parse(stored);
        const defaultsMap = new Map(defaults.map((d) => [d.id, d]));
        // Refresh label/text for default IDs (picks up renames/edits); keep user-added items as-is
        const refreshed = parsed.map((s) => defaultsMap.has(s.id) ? { ...s, ...defaultsMap.get(s.id) } : s);
        const storedIds = new Set(parsed.map((s) => s.id));
        const newDefaults = defaults.filter((d) => !storedIds.has(d.id));
        setSuggestions(newDefaults.length > 0 ? [...refreshed, ...newDefaults] : refreshed);
      }
    } catch { /* ignore */ }
  }, [agentType]);

  // Persist
  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS[agentType], JSON.stringify(suggestions));
  }, [suggestions, agentType]);

  // Close picker on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowPicker(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (editMode) setTimeout(() => labelRef.current?.focus(), FOCUS_DELAY_MS);
  }, [editMode]);

  // ── Helpers ──────────────────────────────────────────────────────────────

  function openAdd() {
    setForm({ icon: autoIcon("", ""), label: "", text: "" });
    setEditMode({ kind: "add" });
    setShowPicker(false);
    setCollapsed(false);
  }

  function openEdit(s: Suggestion) {
    setForm({ icon: s.icon, label: s.label, text: s.text });
    setEditMode({ kind: "edit", id: s.id });
    setShowPicker(false);
  }

  function cancelEdit() { setEditMode(null); setShowPicker(false); }

  function updateField(field: "label" | "text", value: string) {
    const updated = { ...form, [field]: value };
    const wasAuto = form.icon === autoIcon(form.label, form.text) || form.icon === "💬";
    if (wasAuto) updated.icon = autoIcon(updated.label, updated.text);
    setForm(updated);
  }

  function saveForm() {
    const label = form.label.trim();
    const text  = form.text.trim();
    if (!label || !text) return;
    if (editMode?.kind === "add") {
      setSuggestions((p) => [...p, { id: uuidv4(), icon: form.icon, label, text }]);
    } else if (editMode?.kind === "edit") {
      setSuggestions((p) => p.map((s) => s.id === editMode.id ? { ...s, ...form, label, text } : s));
    }
    setEditMode(null); setShowPicker(false);
  }

  function confirmDelete(id: string) {
    setSuggestions((p) => p.filter((s) => s.id !== id));
    setDeleteId(null);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    /*
     * Each agent is a self-contained bordered card.
     * Collapsed → shrink-0. Expanded → flex-1 min-h-0 to share height.
     */
    <div className={`flex flex-col rounded-lg border-2 overflow-hidden ${colors.cardBorder} ${
      collapsed ? "shrink-0" : "flex-1 min-h-0"
    }`}>

      {/* Card header */}
      <div
        className={`shrink-0 flex items-center justify-between px-3 py-2 cursor-pointer
          ${isActive ? colors.cardHeaderBg : "bg-gray-50 hover:bg-gray-100"}
          ${!collapsed ? `border-b ${colors.cardHeaderBorderB}` : ""}
          transition-colors`}
        onClick={onActivate}
      >
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 transition-colors ${isActive ? colors.dot : "bg-gray-300"}`} />
          <span className={`text-xs font-semibold ${isActive ? colors.accent : "text-gray-500"}`}>
            {AGENT_META[agentType].icon} {AGENT_META[agentType].label} Agent
          </span>
          {isActive && (
            <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-semibold border
              ${colors.activeBadgeBg} ${colors.activeBadgeText} ${colors.activeBadgeBorder}`}>
              active
            </span>
          )}
        </div>

        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={openAdd}
            title="Add quick action"
            className={UI.btn.iconAccent}
          >
            <PlusIcon className="w-3 h-3" />
          </button>
          <button
            onClick={() => setCollapsed((v) => !v)}
            className="w-5 h-5 flex items-center justify-center rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <ChevronIcon className={`w-3 h-3 transition-transform ${collapsed ? "-rotate-90" : ""}`} />
          </button>
        </div>
      </div>

      {/* Items — independent scroll inside card */}
      {!collapsed && (
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-2 py-2 flex flex-col gap-1 bg-white">
          {suggestions.map((s) => {
            if (editMode?.kind === "edit" && editMode.id === s.id) {
              return (
                <EditForm
                  key={s.id}
                  form={form}
                  showPicker={showPicker}
                  pickerRef={pickerRef}
                  labelRef={labelRef}
                  onFieldChange={updateField}
                  onIconChange={(icon) => setForm((f) => ({ ...f, icon }))}
                  onTogglePicker={() => setShowPicker((v) => !v)}
                  onSave={saveForm}
                  onCancel={cancelEdit}
                />
              );
            }
            if (deleteId === s.id) {
              return (
                <DeleteConfirm
                  key={s.id}
                  label={s.label}
                  onConfirm={() => confirmDelete(s.id)}
                  onCancel={() => setDeleteId(null)}
                />
              );
            }
            return (
              <SuggestionItem
                key={s.id}
                suggestion={s}
                disabled={disabled || !!editMode}
                onSend={() => {
                  const isDefault = defaults.some(d => d.id === s.id);
                  onActivate();
                  onSuggestion(s.text, s.label, isDefault);
                }}
                onEdit={() => openEdit(s)}
                onDelete={() => setDeleteId(s.id)}
              />
            );
          })}

          {editMode?.kind === "add" && (
            <EditForm
              key="new"
              form={form}
              showPicker={showPicker}
              pickerRef={pickerRef}
              labelRef={labelRef}
              onFieldChange={updateField}
              onIconChange={(icon) => setForm((f) => ({ ...f, icon }))}
              onTogglePicker={() => setShowPicker((v) => !v)}
              onSave={saveForm}
              onCancel={cancelEdit}
            />
          )}

          {suggestions.length === 0 && !editMode && (
            <p className="text-[11px] text-gray-300 text-center py-3">
              No actions yet. Click <strong>+</strong> to add.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function SuggestionItem({
  suggestion, disabled, onSend, onEdit, onDelete,
}: {
  suggestion: Suggestion;
  disabled: boolean;
  onSend: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="group relative flex items-start gap-2 px-2 py-2 rounded-lg border border-transparent hover:bg-indigo-50 hover:border-indigo-200 transition-all duration-150">
      <button
        onClick={onSend}
        disabled={disabled}
        title={suggestion.text}
        className="flex items-start gap-2 flex-1 min-w-0 text-left disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <span className="flex-shrink-0 mt-0.5 w-6 h-6 rounded-md bg-gray-100 group-hover:bg-indigo-100 flex items-center justify-center text-xs transition-colors">
          {suggestion.icon}
        </span>
        <span className="flex flex-col min-w-0">
          <span className="text-xs font-semibold text-gray-700 group-hover:text-indigo-700 truncate leading-tight">
            {suggestion.label}
          </span>
          <span className="text-[11px] text-gray-400 group-hover:text-indigo-500 leading-snug line-clamp-2 mt-0.5">
            {suggestion.text}
          </span>
        </span>
      </button>
      <div className="flex-shrink-0 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity mt-0.5">
        <button
          onClick={(e) => { e.stopPropagation(); onEdit(); }}
          title="Edit"
          className={UI.btn.iconAccent}
        >
          <PencilIcon className="w-3 h-3" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          title="Delete"
          className={UI.btn.iconDanger}
        >
          <TrashIcon className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

function EditForm({
  form, showPicker, pickerRef, labelRef,
  onFieldChange, onIconChange, onTogglePicker, onSave, onCancel,
}: {
  form: { icon: string; label: string; text: string };
  showPicker: boolean;
  pickerRef: React.RefObject<HTMLDivElement | null>;
  labelRef: React.RefObject<HTMLInputElement | null>;
  onFieldChange: (field: "label" | "text", value: string) => void;
  onIconChange: (icon: string) => void;
  onTogglePicker: () => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const valid = form.label.trim() && form.text.trim();
  return (
    <div className={UI.card.form}>
      <div className="flex items-center gap-2 relative">
        <button
          type="button"
          onClick={onTogglePicker}
          className="flex-shrink-0 w-7 h-7 rounded-md bg-white border border-gray-200 hover:border-indigo-300 flex items-center justify-center text-sm shadow-sm"
        >
          {form.icon}
        </button>
        <input
          ref={labelRef}
          type="text"
          placeholder="Short label…"
          value={form.label}
          maxLength={QUICK_ACTION_LABEL_MAX}
          onChange={(e) => onFieldChange("label", e.target.value)}
          onKeyDown={(e) => { if (e.key === KEY_ENTER) onSave(); if (e.key === KEY_ESCAPE) onCancel(); }}
          className={`flex-1 ${UI.input.base}`}
        />
        {showPicker && (
          <div
            ref={pickerRef}
            className="absolute left-0 top-9 z-50 bg-white border border-gray-200 rounded-xl shadow-lg p-2 grid grid-cols-5 gap-1 w-48"
          >
            {ICON_PALETTE.map((emoji) => (
              <button
                key={emoji}
                type="button"
                onClick={() => { onIconChange(emoji); onTogglePicker(); }}
                className={`w-7 h-7 rounded-md flex items-center justify-center text-sm hover:bg-indigo-50 ${form.icon === emoji ? "bg-indigo-100 ring-1 ring-indigo-400" : ""}`}
              >
                {emoji}
              </button>
            ))}
          </div>
        )}
      </div>
      <textarea
        rows={2}
        placeholder="Prompt text sent to the assistant…"
        value={form.text}
        maxLength={QUICK_ACTION_TEXT_MAX}
        onChange={(e) => onFieldChange("text", e.target.value)}
        onKeyDown={(e) => { if (e.key === KEY_ESCAPE) onCancel(); }}
        className={UI.input.textarea}
      />
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className={UI.btn.secondary}>
          Cancel
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={!valid}
          className={`${UI.btn.primary} px-3 py-1`}
        >
          Save
        </button>
      </div>
    </div>
  );
}

function DeleteConfirm({ label, onConfirm, onCancel }: { label: string; onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className={UI.card.danger}>
      <p className="text-[11px] text-red-700 mb-2">Delete <strong>"{label}"</strong>?</p>
      <div className="flex gap-2">
        <button onClick={onCancel} className="flex-1 text-[11px] text-gray-500 border border-gray-200 bg-white rounded-md px-2 py-1">Cancel</button>
        <button onClick={onConfirm} className="flex-1 text-[11px] font-semibold text-white bg-red-500 hover:bg-red-600 rounded-md px-2 py-1">Delete</button>
      </div>
    </div>
  );
}

