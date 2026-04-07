export type MessageRole = "user" | "assistant" | "system";
export type AgentType = "gmail" | "calendar" | "workspace" | "outlook";

export interface NotificationItem {
  id: string;
  type: "agent_complete" | "trigger";
  icon: string;
  title: string;
  timestamp: string;  // formatted display time
  createdAt: number;  // raw ms for ordering
  read: boolean;

  // agent_complete fields
  body?: string;
  draft_subject?: string;
  email_count?: number;
  is_error?: boolean;
  is_processing?: boolean;  // true while summarizer is still running
  inclusion_rule?: string;
  exclusion_rule?: string;
  mode?: string;
  provider?: "Gmail" | "Outlook";

  // trigger fields
  trigger_name?: string;
  payload?: Record<string, unknown>;
}

export interface ToolEvent {
  name: string;
  display: string;
  status: "running" | "done" | "error";
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  displayContent?: string;   // shown in bubble; falls back to content if absent
  tools: ToolEvent[];
  isStreaming: boolean;
  agentType?: AgentType;
  routedTo?: "gmail" | "calendar";
  suggestions?: string[];
}

// SSE event shapes emitted by POST /api/chat/message
export type SSEEvent =
  | { type: "text"; content: string }
  | { type: "tool_start"; name: string; display: string }
  | { type: "tool_end"; name: string; success: boolean }
  | { type: "agent_routed"; agent: "gmail" | "calendar"; reason: string }
  | { type: "suggestions"; items: string[] }
  | { type: "done" }
  | { type: "error"; message: string; error_code?: string };
