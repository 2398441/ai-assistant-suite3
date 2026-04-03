"use client";

import { useState, useRef, useEffect, useCallback, KeyboardEvent } from "react";
import { AgentType } from "@/lib/types";
import { Spinner, SendIcon } from "@/components/ui/icons";
import { SPEECH_RECOGNITION_LANG, KEY_ENTER } from "@/lib/constants";
import { AGENT_META } from "@/lib/agents";

interface MessageInputProps {
  onSend: (message: string, agentType: AgentType, displayText?: string) => void;
  activeAgent: AgentType;
  onAgentChange: (agent: AgentType) => void;
  disabled?: boolean;
  /** When set, populates the textarea for user review before sending. */
  suggestion?: { text: string; label: string; collapsed: boolean; seq: number };
  /** Which agents to show in the selector. Defaults to all AGENT_META keys. */
  availableAgents?: AgentType[];
}


// ── Web Speech API type shim ───────────────────────────────────────────────────
type SpeechRecognitionInstance = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: (e: SpeechRecognitionEvent) => void;
  onerror: (e: SpeechRecognitionErrorEvent) => void;
  onend: () => void;
  start: () => void;
  stop: () => void;
};
type SpeechRecognitionEvent = {
  resultIndex: number;
  results: { [i: number]: { [j: number]: { transcript: string }; isFinal: boolean; length: number } };
};
type SpeechRecognitionErrorEvent = { error: string };

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionInstance;
    webkitSpeechRecognition?: new () => SpeechRecognitionInstance;
  }
}

// ── Voice hook ────────────────────────────────────────────────────────────────

type VoiceState = "idle" | "listening" | "unsupported";

function useVoiceInput(onTranscript: (text: string) => void) {
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);

  // Detect support once on mount
  const supported =
    typeof window !== "undefined" &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  const startListening = useCallback(() => {
    if (!supported) { setVoiceState("unsupported"); return; }

    const SR = window.SpeechRecognition ?? window.webkitSpeechRecognition!;
    const recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = SPEECH_RECOGNITION_LANG;

    recognition.onresult = (e: SpeechRecognitionEvent) => {
      let interim = "";
      let final = "";
      for (let i = e.resultIndex; i < Object.keys(e.results).length; i++) {
        const result = e.results[i];
        if (result.isFinal) final += result[0].transcript;
        else interim += result[0].transcript;
      }
      // Show interim as preview; commit final
      onTranscript(final || interim);
    };

    recognition.onerror = () => setVoiceState("idle");
    recognition.onend   = () => setVoiceState("idle");

    recognitionRef.current = recognition;
    recognition.start();
    setVoiceState("listening");
  }, [supported, onTranscript]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setVoiceState("idle");
  }, []);

  const toggle = useCallback(() => {
    if (voiceState === "listening") stopListening();
    else startListening();
  }, [voiceState, startListening, stopListening]);

  return { voiceState, toggle, supported };
}

// ── Component ─────────────────────────────────────────────────────────────────

export function MessageInput({
  onSend,
  activeAgent,
  onAgentChange,
  disabled,
  suggestion,
  availableAgents,
}: MessageInputProps) {
  const agentKeys = availableAgents ?? (Object.keys(AGENT_META) as AgentType[]);
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isCollapsed  = useRef(false);
  const fullTextRef  = useRef("");

  // Append voice transcript to whatever is already typed
  const handleTranscript = useCallback((transcript: string) => {
    setValue((prev) => {
      const base = prev.trimEnd();
      return base ? `${base} ${transcript}` : transcript;
    });
    // Resize textarea
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    });
  }, []);

  const { voiceState, toggle, supported } = useVoiceInput(handleTranscript);

  // Populate textarea when a quick-action suggestion is selected
  useEffect(() => {
    if (!suggestion?.text) return;
    if (suggestion.collapsed && suggestion.label) {
      isCollapsed.current = true;
      fullTextRef.current = suggestion.text;
      setValue(suggestion.label);
    } else {
      isCollapsed.current = false;
      fullTextRef.current = "";
      setValue(suggestion.text);
    }
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    });
  }, [suggestion?.seq]);

  function handleSend() {
    if (isCollapsed.current && fullTextRef.current) {
      const displayText = value.trim();
      const textToSend  = fullTextRef.current.trim();
      isCollapsed.current = false;
      fullTextRef.current = "";
      if (!textToSend || disabled) return;
      onSend(textToSend, activeAgent, displayText);
      setValue("");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
      return;
    }
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, activeAgent);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // While showing collapsed label — intercept all keys
    if (isCollapsed.current && fullTextRef.current) {
      if (e.key === KEY_ENTER && !e.shiftKey) {
        e.preventDefault();
        handleSend();
        return;
      }
      // Any other key: expand to full prompt
      const full = fullTextRef.current;
      isCollapsed.current = false;
      fullTextRef.current = "";
      if (e.key.length === 1) {
        // Printable char — append it to the full text
        e.preventDefault();
        setValue(full + e.key);
      } else {
        // Non-printable (Backspace, arrows, etc.) — just expand
        e.preventDefault();
        setValue(full);
      }
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = "auto";
        el.style.height = `${el.scrollHeight}px`;
        el.setSelectionRange(el.value.length, el.value.length);
      });
      return;
    }
    if (e.key === KEY_ENTER && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleInput() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }

  const isListening = voiceState === "listening";

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3 space-y-2">
      {/* Agent selector */}
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-gray-400 mr-1">Sending to:</span>
        {agentKeys.map((type) => (
          <button
            key={type}
            onClick={() => onAgentChange(type)}
            disabled={disabled}
            className={`
              flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border
              transition-all disabled:cursor-not-allowed
              ${activeAgent === type
                ? `${AGENT_META[type].colors.selectorBtn} shadow-sm`
                : "bg-white text-gray-400 border-gray-200 hover:border-gray-300 hover:text-gray-600"}
            `}
          >
            <span>{AGENT_META[type].icon}</span>
            <span>{AGENT_META[type].label} Agent</span>
            {activeAgent === type && (
              <span className={`w-1.5 h-1.5 rounded-full ${AGENT_META[type].colors.ring} inline-block`} />
            )}
          </button>
        ))}
      </div>

      {/* Text input + mic + send */}
      <div className={`flex items-end gap-2 bg-gray-50 border rounded-xl px-3 py-2 transition-all
        ${isListening
          ? "border-red-400 ring-1 ring-red-300"
          : "border-gray-200 focus-within:border-indigo-400 focus-within:ring-1 focus-within:ring-indigo-300"}`}
      >
        <textarea
          ref={textareaRef}
          rows={1}
          placeholder={
            isListening
              ? "Listening… speak now"
              : disabled
              ? "Waiting for response…"
              : activeAgent === "workspace"
              ? "Ask anything about Gmail, Calendar, or both…"
              : `Message ${AGENT_META[activeAgent].label} Agent directly…`
          }
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          disabled={disabled}
          className="flex-1 bg-transparent text-sm text-gray-900 placeholder-gray-400 resize-none outline-none min-h-[24px] leading-6 disabled:cursor-not-allowed"
        />

        {/* Mic button — hidden if browser unsupported */}
        {supported && (
          <button
            onClick={toggle}
            disabled={disabled}
            title={isListening ? "Stop listening" : "Voice input"}
            className={`flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed
              ${isListening
                ? "bg-red-500 hover:bg-red-600 text-white"
                : "bg-gray-100 hover:bg-gray-200 text-gray-500 hover:text-gray-700"}`}
            aria-label={isListening ? "Stop voice input" : "Start voice input"}
          >
            {isListening ? <StopIcon /> : <MicIcon />}
          </button>
        )}

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Send message"
        >
          {disabled ? (
            <Spinner className="w-4 h-4 animate-spin" />
          ) : (
            <SendIcon className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Status bar */}
      <p className="text-xs text-gray-400 text-center">
        {isListening
          ? <span className="text-red-500 font-medium flex items-center justify-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse inline-block" />
              Listening — speak your message, then click 🎤 or review &amp; press Enter
            </span>
          : "Enter to send · Shift+Enter for new line · 🎤 for voice"}
      </p>
    </div>
  );
}

// ── SVG icons ─────────────────────────────────────────────────────────────────

function MicIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}
