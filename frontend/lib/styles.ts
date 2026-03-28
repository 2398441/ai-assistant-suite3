/**
 * Shared UI pattern tokens — Tailwind class strings for recurring UI patterns.
 *
 * Import the UI namespace in any component that needs shared styling:
 *   import { UI } from "@/lib/styles";
 *
 * Component-specific layout, agent-specific colours, and one-off styles stay inline.
 * Only patterns that appear in ≥2 components (or establish a clear convention) live here.
 */

export const UI = {
  /** Button variants */
  btn: {
    /** Primary action (indigo). Caller adds px/py and any layout classes. */
    primary:    "text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors",
    /** Ghost cancel / secondary text button */
    secondary:  "text-[11px] text-gray-400 hover:text-gray-600 px-2 py-1 rounded",
    /** Small (20×20) icon button — accent hover (indigo) */
    iconAccent: "w-5 h-5 flex items-center justify-center rounded text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors",
    /** Small (20×20) icon button — danger hover (red) */
    iconDanger: "w-5 h-5 flex items-center justify-center rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors",
    /** Medium (28×28) close / dismiss icon button */
    iconClose:  "w-7 h-7 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors",
  },

  /** Input / textarea variants */
  input: {
    /** Compact inline text field (edit forms) */
    base:     "text-xs px-2 py-1.5 rounded-md border border-gray-200 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-400 placeholder-gray-300",
    /** Compact textarea (edit forms) */
    textarea: "w-full text-xs px-2 py-1.5 rounded-md border border-gray-200 bg-white resize-none focus:outline-none focus:ring-1 focus:ring-indigo-400 placeholder-gray-300 leading-relaxed",
    /** Settings panel field (slightly larger, monospaced, transitions bg on focus) */
    settings: "w-full text-xs px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400 focus:bg-white placeholder-gray-300 font-mono transition-colors",
  },

  /** Badge / pill variants */
  badge: {
    /** Quick-reply suggestion chip (MessageBubble) */
    suggestion:    "px-3 py-1.5 text-xs font-medium rounded-full border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 hover:border-indigo-300 transition-colors",
    /** Tool-event status: running */
    statusRunning: "bg-amber-50 border-amber-200 text-amber-700",
    /** Tool-event status: done */
    statusDone:    "bg-green-50 border-green-200 text-green-700",
    /** Tool-event status: error */
    statusError:   "bg-red-50 border-red-200 text-red-700",
    /** Small inline "updated / saved" pill */
    savedPill:     "text-[9px] font-semibold text-green-600 bg-green-50 border border-green-200 px-1.5 py-0.5 rounded-full",
  },

  /** Card wrapper variants */
  card: {
    /** Form card (add / edit quick action) */
    form:   "rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-2.5 space-y-2",
    /** Destructive / danger confirmation card */
    danger: "rounded-lg border border-red-200 bg-red-50 px-2.5 py-2",
  },

  /** Inline alert banners */
  alert: {
    error:   "text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2",
    success: "text-xs text-green-600 bg-green-50 border border-green-200 rounded-lg px-3 py-2",
  },
} as const;
