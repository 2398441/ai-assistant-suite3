"use client";

import { Message, ToolEvent, AgentType } from "@/lib/types";
import { AGENT_META } from "@/lib/agents";
import { UI } from "@/lib/styles";
import { FormattedContent } from "@/components/ui/MarkdownContent";
import { TYPING_INDICATOR_STAGGER_S } from "@/lib/constants";

interface MessageBubbleProps {
  message: Message;
  onSuggestion?: (text: string, agentType: AgentType) => void;
}

export function MessageBubble({ message, onSuggestion }: MessageBubbleProps) {
  const isUser = message.role === "user";

  // ── System messages ───────────────────────────────────────────────────────
  if (message.role === "system") {
    return (
      <div className="flex justify-center">
        <div className="max-w-[85%] px-4 py-2.5 rounded-xl text-xs bg-amber-50 border border-amber-200 text-amber-800 shadow-sm">
          <FormattedContent content={message.content} />
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {/* Assistant avatar */}
      {!isUser && (
        <div className="flex flex-col items-center gap-1">
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center shadow-sm">
            <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
              />
            </svg>
          </div>
          {message.agentType
            ? <AgentBadge agentType={message.agentType} />
            : null
          }
        </div>
      )}

      <div className={`max-w-[75%] flex flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>
        {/* Tool use indicators */}
        {message.tools.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.tools.map((tool, i) => (
              <ToolBadge key={i} tool={tool} />
            ))}
          </div>
        )}

        {/* Message bubble */}
        {(message.content || message.isStreaming) && (
          <div className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
            isUser
              ? "bg-indigo-600 text-white rounded-tr-sm"
              : "bg-white text-gray-800 border border-gray-200 rounded-tl-sm shadow-sm"
          }`}>
            {isUser ? (
              <span className="whitespace-pre-wrap">{message.displayContent ?? message.content}</span>
            ) : (
              <div className="prose prose-sm max-w-none">
                <FormattedContent
                  content={message.content}
                  onEditableBlock={(text) => onSuggestion?.(text, message.agentType ?? "workspace")}
                />
                {message.isStreaming && !message.content && <TypingIndicator />}
                {message.isStreaming && message.content && (
                  <span className="inline-block w-1.5 h-4 bg-gray-400 animate-pulse ml-0.5 align-middle rounded-sm" />
                )}
              </div>
            )}
          </div>
        )}

        {/* Streaming skeleton when no content yet */}
        {message.isStreaming && !message.content && message.tools.length === 0 && (
          <div className="px-4 py-2.5 rounded-2xl rounded-tl-sm bg-white border border-gray-200 shadow-sm">
            <TypingIndicator />
          </div>
        )}

        {/* Suggestion chips — shown after streaming completes */}
        {!message.isStreaming && message.suggestions && message.suggestions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {message.suggestions.map((text, i) => (
              <button
                key={i}
                onClick={() => onSuggestion?.(text, message.agentType ?? "workspace")}
                className={UI.badge.suggestion}
              >
                {text}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
          <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
            />
          </svg>
        </div>
      )}
    </div>
  );
}

// ── Agent / routing badges ────────────────────────────────────────────────────

function AgentBadge({ agentType }: { agentType: AgentType }) {
  const { icon, label, colors } = AGENT_META[agentType];
  return (
    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-semibold border ${colors.badge} whitespace-nowrap`}>
      {icon} {label}
    </span>
  );
}

function RoutingBadge({ routedTo }: { routedTo: "gmail" | "calendar" }) {
  const { icon, label } = AGENT_META[routedTo];
  return (
    <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-semibold border bg-indigo-50 text-indigo-600 border-indigo-200 whitespace-nowrap">
      🤖 → {icon} {label}
    </span>
  );
}

// ── Tool badge ────────────────────────────────────────────────────────────────

function ToolBadge({ tool }: { tool: ToolEvent }) {
  const statusColors: Record<ToolEvent["status"], string> = {
    running: UI.badge.statusRunning,
    done:    UI.badge.statusDone,
    error:   UI.badge.statusError,
  };

  const icons: Record<ToolEvent["status"], React.ReactNode> = {
    running: (
      <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>
    ),
    done: (
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
    error: (
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
  };

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${statusColors[tool.status]}`}>
      {icons[tool.status]}
      {tool.display}
    </span>
  );
}

// ── Typing indicator ──────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <span className="inline-flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
          style={{ animationDelay: `${i * TYPING_INDICATOR_STAGGER_S}s` }}
        />
      ))}
    </span>
  );
}
