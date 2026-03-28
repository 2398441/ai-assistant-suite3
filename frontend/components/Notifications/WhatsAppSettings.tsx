"use client";

import { useEffect, useRef, useState } from "react";
import { getWhatsAppSettings, saveWhatsAppSettings, sendTestWhatsApp } from "@/lib/api";
import { Spinner, CheckIcon, CloseIcon, SendIcon } from "@/components/ui/icons";

interface Props {
  userEmail: string;
}

function WAIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg">
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
    </svg>
  );
}

export function WhatsAppSettings({ userEmail }: Props) {
  const [open, setOpen]             = useState(false);
  const [number, setNumber]         = useState("");
  const [enabled, setEnabled]       = useState(false);
  const [sandboxKeyword, setSandboxKeyword] = useState("");
  const [saving, setSaving]         = useState(false);
  const [testing, setTesting]       = useState(false);
  const [loading, setLoading]       = useState(true);
  const [status, setStatus]         = useState<{ ok: boolean; msg: string } | null>(null);
  const panelRef                    = useRef<HTMLDivElement>(null);

  // Load settings on mount — restores persisted number + enabled state immediately
  useEffect(() => {
    if (!userEmail) return;
    setLoading(true);
    getWhatsAppSettings(userEmail).then((s) => {
      setNumber(s.whatsapp_number ?? "");
      setEnabled(s.enabled ?? false);
      setSandboxKeyword(s.sandbox_keyword ?? "");
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [userEmail]);

  // Refresh when panel is opened (picks up any server-side changes)
  useEffect(() => {
    if (!open) return;
    getWhatsAppSettings(userEmail).then((s) => {
      setNumber(s.whatsapp_number ?? "");
      setEnabled(s.enabled ?? false);
      setSandboxKeyword(s.sandbox_keyword ?? "");
      setStatus(null);
    });
  }, [open, userEmail]);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  async function handleSave() {
    setSaving(true);
    setStatus(null);
    const result = await saveWhatsAppSettings(userEmail, number, enabled);
    setSaving(false);
    setStatus(result.ok
      ? { ok: true,  msg: "Settings saved" }
      : { ok: false, msg: result.error ?? "Save failed" }
    );
  }

  async function handleTest() {
    if (!number) return;
    setTesting(true);
    setStatus(null);
    const result = await sendTestWhatsApp(userEmail, number);
    setTesting(false);
    setStatus(result.ok
      ? { ok: true,  msg: "Test message sent — check your WhatsApp" }
      : { ok: false, msg: result.error ?? "Send failed" }
    );
  }

  // Derived visual state for the trigger button
  const btnState: "loading" | "active" | "partial" | "off" =
    loading        ? "loading"
    : enabled && number ? "active"
    : enabled       ? "partial"
    : "off";

  const btnCls = {
    loading: "text-gray-400 bg-gray-50 border-gray-200 cursor-wait",
    active:  "text-green-700 bg-green-50 border-green-200 hover:bg-green-100",
    partial: "text-amber-700 bg-amber-50 border-amber-200 hover:bg-amber-100",
    off:     "text-gray-600 bg-gray-50 border-gray-200 hover:bg-gray-100",
  }[btnState];

  const isBusy = saving || testing;

  // Connection status shown in the panel header
  const connLabel =
    enabled && number ? "Active"
    : enabled          ? "No number set"
    : "Disabled";
  const connCls =
    enabled && number ? "bg-green-100 text-green-700 border-green-200"
    : enabled          ? "bg-amber-100 text-amber-700 border-amber-200"
    : "bg-gray-100 text-gray-500 border-gray-200";
  const connDotCls =
    enabled && number ? "bg-green-500 animate-pulse"
    : enabled          ? "bg-amber-400"
    : "bg-gray-300";

  return (
    <div className="relative" ref={panelRef}>
      {/* ── Trigger button ──────────────────────────────────────────────── */}
      <button
        onClick={() => setOpen((v) => !v)}
        title="WhatsApp notifications"
        disabled={loading}
        className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${btnCls}`}
      >
        {loading ? (
          <Spinner className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <WAIcon className="w-3.5 h-3.5 fill-current" />
        )}
        <span>{loading ? "WA" : enabled && number ? "WA On" : enabled ? "WA ⚠" : "WA"}</span>
        {/* Live status dot — only when not loading */}
        {!loading && (
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            enabled && number ? "bg-green-500 animate-pulse"
            : enabled          ? "bg-amber-400"
            : "bg-gray-300"
          }`} />
        )}
      </button>

      {/* ── Dropdown panel ──────────────────────────────────────────────── */}
      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-72 bg-white rounded-xl shadow-lg border border-gray-200 z-50 overflow-hidden">

          {/* Header */}
          <div className="px-4 py-3 bg-green-50 border-b border-green-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <WAIcon className="w-4 h-4 fill-green-600" />
              <span className="text-sm font-semibold text-green-800">WhatsApp Notifications</span>
            </div>
            {/* Connection status chip */}
            <span className={`flex items-center gap-1 text-[9px] font-semibold px-1.5 py-0.5 rounded-full border ${connCls}`}>
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${connDotCls}`} />
              {connLabel}
            </span>
          </div>

          {/* Indeterminate progress bar — visible while saving or testing */}
          <div className={`relative h-1 overflow-hidden transition-opacity duration-200 ${isBusy ? "opacity-100" : "opacity-0"}`}>
            <div className={`absolute inset-y-0 w-1/3 rounded-full animate-indeterminate ${
              testing ? "bg-green-400" : "bg-indigo-400"
            }`} />
          </div>

          <div className="px-4 py-3 space-y-3">
            {/* Sandbox hint */}
            <p className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5 leading-relaxed">
              <strong>Sandbox mode:</strong> First send{" "}
              <code className="font-mono bg-amber-100 px-0.5 rounded">
                join {sandboxKeyword || "…"}
              </code>{" "}
              to <strong>+1 415 523 8886</strong> on WhatsApp to activate.
            </p>

            {/* Phone number input */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Your WhatsApp number
              </label>
              <input
                type="tel"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
                placeholder="+919XXXXXXXXX"
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-green-400 focus:border-transparent"
              />
              <p className="text-[10px] text-gray-400 mt-0.5">E.164 format — include country code</p>
            </div>

            {/* Enable toggle */}
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-700">Enable notifications</span>
              <button
                onClick={() => setEnabled((v) => !v)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                  enabled ? "bg-green-500" : "bg-gray-300"
                }`}
              >
                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                  enabled ? "translate-x-4" : "translate-x-0.5"
                }`} />
              </button>
            </div>

            {/* Status feedback */}
            {status && (
              <div className={`flex items-start gap-2 text-[11px] rounded-lg px-2.5 py-1.5 ${
                status.ok
                  ? "bg-green-50 text-green-700 border border-green-200"
                  : "bg-red-50 text-red-700 border border-red-200"
              }`}>
                <span className="flex-shrink-0 mt-px">
                  {status.ok
                    ? <CheckIcon className="w-3 h-3" strokeWidth={2.5} />
                    : <CloseIcon className="w-3 h-3" strokeWidth={2.5} />
                  }
                </span>
                <span>{status.msg}</span>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-1">
              <button
                onClick={handleTest}
                disabled={testing || !number}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-medium rounded-lg border border-green-300 text-green-700 bg-green-50 hover:bg-green-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {testing ? (
                  <>
                    <Spinner className="w-3 h-3 animate-spin" />
                    Dispatching…
                  </>
                ) : (
                  <>
                    <SendIcon className="w-3 h-3" />
                    Send test
                  </>
                )}
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? (
                  <>
                    <Spinner className="w-3 h-3 animate-spin" />
                    Saving…
                  </>
                ) : (
                  <>
                    <CheckIcon className="w-3 h-3" />
                    Save
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
