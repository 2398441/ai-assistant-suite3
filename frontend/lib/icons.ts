/**
 * Icon registry for quick-action suggestions.
 *
 * ICON_RULES  — maps keyword patterns to an emoji; drives autoIcon()
 * ICON_PALETTE — ordered list shown in the emoji picker inside the edit form
 * autoIcon()  — derives the best emoji for a given label + prompt text
 *
 * To add support for a new keyword: add a row to ICON_RULES.
 * To add an emoji to the picker:    append it to ICON_PALETTE.
 * Components never hardcode suggestion icons — they call autoIcon() instead.
 */

export const ICON_RULES: [RegExp, string][] = [
  [/email|mail|inbox|unread|send|reply|thread/i, "📧"],
  [/digest|summary|summaris/i,                   "📊"],
  [/draft|compose|write/i,                       "✍️"],
  [/urgent|flag|important|critical/i,            "🚨"],
  [/await|pending|unanswered|follow.?up/i,       "⏰"],
  [/organis|archive|label|clean|dedup/i,         "🗂️"],
  [/sender|who|contact/i,                        "👥"],
  [/today|schedule|event/i,                      "📅"],
  [/week|meeting|calendar/i,                     "📆"],
  [/free|slot|availability/i,                    "🔍"],
  [/create|add|new|quick/i,                      "➕"],
  [/deadline|reminder|upcoming/i,                "🔄"],
  [/invite|attendee|rsvp/i,                      "🤝"],
  [/search|find|look/i,                          "🔎"],
  [/notify|alert|whatsapp|share|send.*action/i,  "📲"],
  [/document|file|attachment/i,                  "📂"],
  [/report|data|analytics/i,                     "📈"],
  [/task|action|checklist/i,                     "✅"],
  [/brief|morning|overview/i,                    "📋"],
  [/feature|tool|capability/i,                   "🛠️"],
];

export const ICON_PALETTE: string[] = [
  "📧", "📬", "📨", "📤", "📥",
  "📅", "📆", "🗓️", "⏰", "⏳",
  "📊", "📈", "💼", "📋", "📂",
  "✍️", "📝", "💬", "🤝", "✅",
  "🚨", "🔔", "🔍", "⚡", "🎯",
  "➕", "🔄", "👥", "🗂️", "🔎",
];

/** Derive the best emoji for a suggestion based on its label and prompt text.
 *  Falls back to 💬 when no rule matches. */
export function autoIcon(label: string, text: string): string {
  const combined = `${label} ${text}`;
  for (const [regex, icon] of ICON_RULES) {
    if (regex.test(combined)) return icon;
  }
  return "💬";
}
