/**
 * Agent metadata — single source of truth for agent icons, labels and colours.
 *
 * icon + label  — display content, imported by every component that renders an agent name.
 * colors        — all per-agent Tailwind class tokens, imported by components that need
 *                 agent-specific styling.  Component layout/structure classes stay inline;
 *                 only the colour tokens that vary per agent live here.
 */

import { AgentType } from "./types";

export interface AgentColors {
  /** Accent text colour  e.g. "text-purple-600" */
  accent: string;
  /** Solid background for status dots / card indicator  e.g. "bg-purple-500" */
  dot: string;
  /** Solid background for the active ring in selector pills  e.g. "bg-purple-600" */
  ring: string;
  /** Full class string for agent selector pill button (bg + text + border + hover) */
  selectorBtn: string;
  /** Inline agent badge (bg + text + border) */
  badge: string;
  /** Card outer border */
  cardBorder: string;
  /** Card header background */
  cardHeaderBg: string;
  /** Card header bottom border */
  cardHeaderBorderB: string;
  /** "active" status badge background */
  activeBadgeBg: string;
  /** "active" status badge text */
  activeBadgeText: string;
  /** "active" status badge border */
  activeBadgeBorder: string;
}

export const AGENT_META: Record<AgentType, { icon: string; label: string; colors: AgentColors }> = {
  workspace: {
    icon:  "🏢",
    label: "Workspace",
    colors: {
      accent:             "text-purple-600",
      dot:                "bg-purple-500",
      ring:               "bg-purple-600",
      selectorBtn:        "bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100",
      badge:              "bg-purple-50 text-purple-600 border-purple-200",
      cardBorder:         "border-purple-200",
      cardHeaderBg:       "bg-purple-50",
      cardHeaderBorderB:  "border-purple-200",
      activeBadgeBg:      "bg-purple-100",
      activeBadgeText:    "text-purple-700",
      activeBadgeBorder:  "border-purple-200",
    },
  },
  gmail: {
    icon:  "📧",
    label: "Gmail",
    colors: {
      accent:             "text-rose-600",
      dot:                "bg-rose-500",
      ring:               "bg-rose-600",
      selectorBtn:        "bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100",
      badge:              "bg-rose-50 text-rose-600 border-rose-200",
      cardBorder:         "border-rose-200",
      cardHeaderBg:       "bg-rose-50",
      cardHeaderBorderB:  "border-rose-200",
      activeBadgeBg:      "bg-rose-100",
      activeBadgeText:    "text-rose-700",
      activeBadgeBorder:  "border-rose-200",
    },
  },
  calendar: {
    icon:  "📅",
    label: "Calendar",
    colors: {
      accent:             "text-blue-600",
      dot:                "bg-blue-500",
      ring:               "bg-blue-600",
      selectorBtn:        "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100",
      badge:              "bg-blue-50 text-blue-600 border-blue-200",
      cardBorder:         "border-blue-200",
      cardHeaderBg:       "bg-blue-50",
      cardHeaderBorderB:  "border-blue-200",
      activeBadgeBg:      "bg-blue-100",
      activeBadgeText:    "text-blue-700",
      activeBadgeBorder:  "border-blue-200",
    },
  },
};
