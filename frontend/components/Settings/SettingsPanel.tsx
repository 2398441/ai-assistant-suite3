"use client";

import { useState, useEffect, useCallback } from "react";
import { getSettings, updateSettings, SettingItem } from "@/lib/api";
import { GearIcon, CloseIcon, CheckIcon, EyeIcon, EyeOffIcon, Spinner } from "@/components/ui/icons";
import { UI } from "@/lib/styles";

type SaveState = "idle" | "saving" | "saved" | "error";

export function SettingsPanel() {
  const [open, setOpen]           = useState(false);
  const [items, setItems]         = useState<SettingItem[]>([]);
  const [edits, setEdits]         = useState<Record<string, string>>({});
  const [revealed, setRevealed]   = useState<Record<string, boolean>>({});
  const [loadError, setLoadError] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedKeys, setSavedKeys] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const data = await getSettings();
      setItems(data);
      // Initialise edits with the masked/current values so the form is pre-filled
      const init: Record<string, string> = {};
      data.forEach((s) => { init[s.key] = s.value; });
      setEdits(init);
    } catch {
      setLoadError("Could not load settings from backend.");
    }
  }, []);

  useEffect(() => {
    if (open) load();
    else {
      // Reset transient state when closing
      setRevealed({});
      setSaveState("idle");
      setSavedKeys([]);
    }
  }, [open, load]);

  async function handleSave() {
    setSaveState("saving");
    try {
      // Only send keys that have been changed from the original masked value
      const updates: Record<string, string> = {};
      items.forEach((s) => {
        const edited = edits[s.key] ?? "";
        // Skip if still shows the original masked value (user didn't change it)
        if (edited && edited !== s.value) {
          updates[s.key] = edited;
        }
      });

      if (Object.keys(updates).length === 0) {
        setSaveState("saved");
        setSavedKeys([]);
        setTimeout(() => setSaveState("idle"), 2000);
        return;
      }

      const result = await updateSettings(updates);
      setSaveState("saved");
      setSavedKeys(result.updated);
      // Refresh displayed values
      await load();
      setTimeout(() => { setSaveState("idle"); setSavedKeys([]); }, 3000);
    } catch (err) {
      setSaveState("error");
      setTimeout(() => setSaveState("idle"), 4000);
    }
  }

  return (
    <>
      {/* Gear button in header */}
      <button
        onClick={() => setOpen(true)}
        title="Backend settings"
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 hover:border-gray-300 transition-colors"
      >
        <GearIcon className="w-3.5 h-3.5" />
        Settings
      </button>

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Slide-in panel */}
      <div className={`fixed top-0 right-0 h-full w-[420px] bg-white shadow-2xl z-50 flex flex-col
        transition-transform duration-300 ease-out
        ${open ? "translate-x-0" : "translate-x-full"}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
          <div className="flex items-center gap-2">
            <GearIcon className="w-4 h-4 text-gray-500" />
            <span className="font-semibold text-gray-800 text-sm">Backend Settings</span>
          </div>
          <button
            onClick={() => setOpen(false)}
            className={UI.btn.iconClose}
          >
            <CloseIcon className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {loadError && (
            <div className={UI.alert.error}>
              {loadError}
            </div>
          )}

          <p className="text-[11px] text-gray-400 leading-relaxed">
            Changes are applied immediately in memory and persisted to{" "}
            <code className="bg-gray-100 px-1 py-0.5 rounded text-gray-600">backend/.env</code>.
            Sensitive values are masked — enter a new value to replace, or leave as-is to keep current.
          </p>

          {items.length === 0 && !loadError && (
            <div className="flex items-center justify-center py-12">
              <Spinner className="w-5 h-5 text-indigo-400 animate-spin" />
            </div>
          )}

          {items.map((s) => (
            <SettingField
              key={s.key}
              item={s}
              value={edits[s.key] ?? ""}
              revealed={!!revealed[s.key]}
              saved={savedKeys.includes(s.key)}
              onChange={(v) => setEdits((prev) => ({ ...prev, [s.key]: v }))}
              onToggleReveal={() => setRevealed((prev) => ({ ...prev, [s.key]: !prev[s.key] }))}
            />
          ))}
        </div>

        {/* Footer */}
        <div className="shrink-0 px-5 py-4 border-t border-gray-200 flex items-center justify-between gap-3">
          <p className="text-[10px] text-gray-400">
            {saveState === "saved" && savedKeys.length > 0
              ? `✓ Saved: ${savedKeys.join(", ")}`
              : saveState === "saved"
              ? "✓ No changes to save"
              : saveState === "error"
              ? "⚠️ Save failed — check backend logs"
              : "Unsaved changes take effect immediately on save"}
          </p>
          <button
            onClick={handleSave}
            disabled={saveState === "saving"}
            className={`${UI.btn.primary} flex items-center gap-1.5 px-4 py-2`}
          >
            {saveState === "saving" ? (
              <><Spinner className="w-3.5 h-3.5 animate-spin" /> Saving…</>
            ) : saveState === "saved" ? (
              <><CheckIcon className="w-3.5 h-3.5" /> Saved</>
            ) : (
              "Save Changes"
            )}
          </button>
        </div>
      </div>
    </>
  );
}

// ── Individual field ───────────────────────────────────────────────────────────

function SettingField({
  item, value, revealed, saved, onChange, onToggleReveal,
}: {
  item: SettingItem;
  value: string;
  revealed: boolean;
  saved: boolean;
  onChange: (v: string) => void;
  onToggleReveal: () => void;
}) {
  const inputType = item.sensitive && !revealed ? "password" : "text";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label className="text-xs font-semibold text-gray-700">{item.label}</label>
        <div className="flex items-center gap-1.5">
          {saved && (
            <span className={UI.badge.savedPill}>
              updated
            </span>
          )}
          <span className="text-[9px] font-mono text-gray-300">{item.key}</span>
        </div>
      </div>
      <div className="relative flex items-center">
        <input
          type={inputType}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={item.sensitive ? "Enter new value to replace…" : ""}
          className={`${UI.input.settings} pr-9`}
        />
        {item.sensitive && (
          <button
            type="button"
            onClick={onToggleReveal}
            className="absolute right-2.5 text-gray-400 hover:text-gray-600 transition-colors"
            title={revealed ? "Hide" : "Reveal"}
          >
            {revealed
              ? <EyeOffIcon className="w-3.5 h-3.5" />
              : <EyeIcon className="w-3.5 h-3.5" />
            }
          </button>
        )}
      </div>
    </div>
  );
}
