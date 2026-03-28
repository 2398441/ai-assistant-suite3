"use client";

import { useEffect, useRef, useState } from "react";
import { Message, AgentType } from "@/lib/types";
import { MessageBubble } from "./MessageBubble";

const EMPTY_STATE_PROMPTS: { headline: string; sub: string }[] = [
  { headline: "What's on your mind?",            sub: "Ask about emails, meetings, drafts, or anything on your agenda." },
  { headline: "Your inbox awaits.",               sub: "I can summarise threads, draft replies, or check your calendar." },
  { headline: "Ready when you are.",             sub: "Try asking about recent emails or upcoming events." },
  { headline: "Let's get things done.",          sub: "Ask me to find an email, schedule a meeting, or clear your drafts." },
  { headline: "Good to see you back.",           sub: "Need a catch-up on emails, or want to check today's schedule?" },
  { headline: "What would you like to tackle?",  sub: "Gmail and Google Calendar are both at your fingertips." },
  { headline: "Pick up where you left off.",     sub: "I can pull up recent threads, events, or draft something new." },
];

interface ChatWindowProps {
  messages: Message[];
  onSuggestion?: (text: string, agentType: AgentType) => void;
  userName?: string;
}

export function ChatWindow({ messages, onSuggestion, userName }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [emptyPrompt] = useState(
    () => EMPTY_STATE_PROMPTS[Math.floor(Math.random() * EMPTY_STATE_PROMPTS.length)]
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-6">
        <div className="w-12 h-12 rounded-xl bg-indigo-50 flex items-center justify-center">
          <svg className="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
        </div>
        <div>
          {userName && (
            <p className="text-base font-semibold text-gray-800 mb-1">
              Hi {userName}! 👋
            </p>
          )}
          <p className="font-medium text-gray-700">{emptyPrompt.headline}</p>
          <p className="text-sm text-gray-400 mt-1">{emptyPrompt.sub}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} onSuggestion={onSuggestion} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
