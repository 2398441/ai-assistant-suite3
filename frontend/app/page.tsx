"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { v4 as uuidv4 } from "uuid";

import { ConnectButton } from "@/components/Auth/ConnectButton";
import { ChatWindow } from "@/components/Chat/ChatWindow";
import { MessageInput } from "@/components/Chat/MessageInput";
import { SuggestionsPane } from "@/components/Chat/SuggestionsPane";
import { NotificationListener } from "@/components/Notifications/NotificationListener";
import { NotificationDrawer } from "@/components/Notifications/NotificationDrawer";
import { WhatsAppSettings } from "@/components/Notifications/WhatsAppSettings";
import { TriggerToast } from "@/components/Notifications/TriggerToast";
import { Spinner, SparkleIcon, PlusIcon, LogoutIcon } from "@/components/ui/icons";
import { SettingsPanel } from "@/components/Settings/SettingsPanel";
import { initiateAuth, getAuthStatus, clearMessages, streamMessage, triggerEmailSummarizer, getGreeting, logout, clearSessionToken } from "@/lib/api";
import { Message, SSEEvent, AgentType, NotificationItem } from "@/lib/types";
import {
  GREETING_DISPLAY_DELAY_MS,
  NOTIFICATION_RETENTION_MS,
  STORAGE_KEY_USER_EMAIL,
  STORAGE_KEY_PENDING_EMAIL,
  notificationsStorageKey,
  displayNameStorageKey,
} from "@/lib/constants";

type AppState = "loading" | "unauthenticated" | "chat";

export default function Home() {
  const [appState, setAppState]       = useState<AppState>("loading");
  const [userEmail, setUserEmail]     = useState<string>("");
  const [messages, setMessages]       = useState<Message[]>([]);
  const [isStreaming, setIsStreaming]  = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError]             = useState<string>("");
  const [activeAgent, setActiveAgent] = useState<AgentType>("workspace");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notificationsReady, setNotificationsReady] = useState(false);
  const [suggestion, setSuggestion] = useState<{ text: string; label: string; collapsed: boolean; seq: number } | null>(null);
  const [pendingToast, setPendingToast] = useState<NotificationItem | null>(null);
  const [sidebarNotification, setSidebarNotification] = useState<NotificationItem | null>(null);
  const [userName, setUserName] = useState<string>("");
  const [sidebarWidth, setSidebarWidth] = useState(256);
  const isDragging   = useRef(false);
  const dragStartX   = useRef(0);
  const dragStartW   = useRef(0);

  // ── Sidebar resize ─────────────────────────────────────────────────────────

  useEffect(() => {
    const saved = localStorage.getItem("sidebar_width");
    if (saved) setSidebarWidth(Math.max(180, Math.min(520, parseInt(saved, 10))));
  }, []);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    isDragging.current = true;
    dragStartX.current = e.clientX;
    dragStartW.current = sidebarWidth;
    e.preventDefault();
  }, [sidebarWidth]);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!isDragging.current) return;
      const w = Math.max(180, Math.min(520, dragStartW.current + (e.clientX - dragStartX.current)));
      setSidebarWidth(w);
    }
    function onUp() {
      if (!isDragging.current) return;
      isDragging.current = false;
      setSidebarWidth((w) => { localStorage.setItem("sidebar_width", String(w)); return w; });
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => { document.removeEventListener("mousemove", onMove); document.removeEventListener("mouseup", onUp); };
  }, []);

  // ── On mount ───────────────────────────────────────────────────────────────

  useEffect(() => {
    async function init() {
      const params = new URLSearchParams(window.location.search);
      const callbackEmail = params.get("email");
      if (callbackEmail) {
        localStorage.setItem(STORAGE_KEY_USER_EMAIL, callbackEmail);
        window.history.replaceState({}, "", "/");
        setUserEmail(callbackEmail);
        setAppState("chat");
        setTimeout(() => showGreeting(callbackEmail), GREETING_DISPLAY_DELAY_MS);
        triggerEmailSummarizer(callbackEmail).catch(() => {});
        return;
      }

      const savedEmail = localStorage.getItem(STORAGE_KEY_USER_EMAIL);
      if (savedEmail) {
        try {
          const status = await getAuthStatus(savedEmail);
          if (status.connected) {
            setUserEmail(savedEmail);
            setAppState("chat");
            showGreeting(savedEmail);
            triggerEmailSummarizer(savedEmail).catch(() => {});
            return;
          }
        } catch { /* fall through */ }
        localStorage.removeItem(STORAGE_KEY_USER_EMAIL);
      }
      setAppState("unauthenticated");
    }
    init();
  }, []);

  // ── Restore persisted display name ────────────────────────────────────────

  useEffect(() => {
    if (!userEmail) return;
    const saved = localStorage.getItem(displayNameStorageKey(userEmail));
    if (saved) setUserName(saved);
  }, [userEmail]);

  // ── Notification persistence ───────────────────────────────────────────────

  // Load from localStorage when the user is identified; discard items > 24 h old
  useEffect(() => {
    if (!userEmail) return;
    try {
      const raw = localStorage.getItem(notificationsStorageKey(userEmail));
      const stored: NotificationItem[] = raw ? JSON.parse(raw) : [];
      const cutoff = Date.now() - NOTIFICATION_RETENTION_MS;
      // Strip stale is_processing items — they can never resolve after a page reload
      setNotifications(stored.filter((n) => n.createdAt > cutoff && !n.is_processing));
    } catch {
      setNotifications([]);
    }
    setNotificationsReady(true);
  }, [userEmail]);

  // Save to localStorage on every change (only after initial load to avoid overwrite)
  useEffect(() => {
    if (!userEmail || !notificationsReady) return;
    try {
      localStorage.setItem(notificationsStorageKey(userEmail), JSON.stringify(notifications));
    } catch { /* storage quota exceeded — silently ignore */ }
  }, [notifications, userEmail, notificationsReady]);

  // ── Auth ───────────────────────────────────────────────────────────────────

  async function handleConnect(email: string) {
    setIsConnecting(true);
    setError("");
    try {
      localStorage.setItem(STORAGE_KEY_PENDING_EMAIL, email);
      const callbackUrl = `${window.location.origin}/auth/callback`;
      const result = await initiateAuth(email, callbackUrl, "gmail");
      if (result.connected) {
        localStorage.setItem(STORAGE_KEY_USER_EMAIL, email);
        localStorage.removeItem(STORAGE_KEY_PENDING_EMAIL);
        setUserEmail(email);
        setAppState("chat");
        showGreeting(email);
        triggerEmailSummarizer(email).catch(() => {});
      } else if (result.auth_url) {
        window.location.href = result.auth_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setIsConnecting(false);
    }
  }

  // ── Chat ───────────────────────────────────────────────────────────────────

  const handleSendMessage = useCallback(
    async (content: string, agentType: AgentType = activeAgent, displayText?: string) => {
      if (!userEmail || isStreaming) return;
      setError("");
      setActiveAgent(agentType);

      const userMsg: Message = {
        id: uuidv4(), role: "user", content, displayContent: displayText, tools: [], isStreaming: false,
      };
      const assistantId = uuidv4();
      const assistantMsg: Message = {
        id: assistantId, role: "assistant", content: "", tools: [],
        isStreaming: true, agentType,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      try {
        for await (const event of streamMessage(userEmail, content, agentType)) {
          handleSSEEvent(event, assistantId);
          if (event.type === "done" || event.type === "error") break;
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "";
        if (msg.includes("Invalid or expired session")) {
          handleSignOut();
          return;
        }
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: "Sorry, something went wrong. Please try again.", isStreaming: false }
              : m
          )
        );
      } finally {
        setIsStreaming(false);
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m))
        );
      }
    },
    [userEmail, isStreaming, activeAgent]
  );

  function handleSSEEvent(event: SSEEvent, msgId: string) {
    switch (event.type) {
      case "text":
        setMessages((prev) =>
          prev.map((m) => (m.id === msgId ? { ...m, content: m.content + event.content } : m))
        );
        break;
      case "tool_start":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? { ...m, tools: [...m.tools, { name: event.name, display: event.display, status: "running" }] }
              : m
          )
        );
        break;
      case "tool_end":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? { ...m, tools: m.tools.map((t) => t.name === event.name ? { ...t, status: event.success ? "done" : "error" } : t) }
              : m
          )
        );
        break;
      case "agent_routed":
        setMessages((prev) =>
          prev.map((m) => (m.id === msgId ? { ...m, routedTo: event.agent } : m))
        );
        break;
      case "suggestions":
        setMessages((prev) =>
          prev.map((m) => (m.id === msgId ? { ...m, suggestions: event.items } : m))
        );
        break;
      case "error": {
        const codeBadge = event.error_code ? `[${event.error_code}] ` : "";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? { ...m, content: `⚠️ ${codeBadge}${event.message}`, isStreaming: false }
              : m
          )
        );
        break;
      }
    }
  }

  // ── Quick-action suggestion → populate input for review ───────────────────

  const handleSuggestion = useCallback((text: string, agentType: AgentType, label?: string, isDefault?: boolean) => {
    setActiveAgent(agentType);
    setSuggestion((prev) => ({ text, label: label ?? "", collapsed: isDefault ?? false, seq: (prev?.seq ?? 0) + 1 }));
  }, []);

  // ── Notifications ──────────────────────────────────────────────────────────

  const handleNotification = useCallback((item: NotificationItem) => {
    setNotifications((prev) => {
      // When a real agent_complete arrives, replace any in-flight processing item
      if (item.type === "agent_complete" && !item.is_processing) {
        return [item, ...prev.filter((n) => !(n.type === "agent_complete" && n.is_processing))];
      }
      return [item, ...prev];
    });
    // Sidebar strip shows all notification types (summariser progress + trigger events)
    setSidebarNotification(item);
    // Slide-in toast only for real trigger events (new email, calendar change, etc.)
    if (item.type === "trigger") setPendingToast(item);
  }, []);

  const handleDismissToast = useCallback(() => {
    setPendingToast(null);
  }, []);

  const handleDrawerOpen = useCallback(() => {
    // Opening the bell drawer does NOT dismiss the toast.
    // Toast only disappears when the user clicks ×.
  }, []);

  const handleMarkAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const handleMarkRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  }, []);

  const handleClearNotifications = useCallback(() => {
    setNotifications([]);
  }, []);

  // ── Greeting & conversation ────────────────────────────────────────────────

  async function showGreeting(email: string) {
    try {
      const { greeting, name } = await getGreeting(email);
      if (name) {
        const firstName = name.split(" ")[0];
        setUserName(firstName);
        localStorage.setItem(displayNameStorageKey(email), firstName);
      }
      setMessages((prev) => [
        ...prev,
        { id: uuidv4(), role: "assistant", content: greeting, tools: [], isStreaming: false },
      ]);
    } catch { /* silently skip */ }
  }

  async function handleNewConversation() {
    setMessages([]);
    if (userEmail) {
      try { await clearMessages(userEmail); } catch { /* ignore */ }
      showGreeting(userEmail);
    }
  }

  function handleSignOut() {
    if (userEmail) logout(userEmail).catch(() => {});
    if (userEmail) localStorage.removeItem(notificationsStorageKey(userEmail));
    localStorage.removeItem(STORAGE_KEY_USER_EMAIL);
    localStorage.removeItem(STORAGE_KEY_PENDING_EMAIL);
    clearSessionToken();
    setUserEmail("");
    setUserName("");
    setMessages([]);
    setNotifications([]);
    setNotificationsReady(false);
    setAppState("unauthenticated");
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  if (appState === "loading") {
    return (
      <div className="h-full flex items-center justify-center">
        <Spinner className="w-8 h-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  if (appState === "unauthenticated") {
    return (
      <div className="h-full">
        {error && (
          <div className="fixed top-4 left-1/2 -translate-x-1/2 bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-2 rounded-lg shadow z-50">
            {error}
          </div>
        )}
        <ConnectButton onConnect={handleConnect} isLoading={isConnecting} />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <NotificationListener userEmail={userEmail} onNotification={handleNotification} />

      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white shadow-sm shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center">
            <SparkleIcon className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-gray-800 text-sm">AI Assistant</span>
        </div>

        <div className="flex items-center gap-2">
          {/* New Conversation */}
          <button
            onClick={handleNewConversation}
            disabled={isStreaming || messages.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 hover:border-indigo-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Start a new conversation"
          >
            <PlusIcon className="w-3.5 h-3.5" />
            New Conversation
          </button>

          {/* Connected user */}
          <div className="flex items-center gap-1.5 text-xs text-green-600 px-2 py-1.5 bg-green-50 rounded-lg border border-green-200">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
            {userName || userEmail}
          </div>

          {/* Backend settings */}
          <SettingsPanel />

          {/* WhatsApp settings */}
          <WhatsAppSettings userEmail={userEmail} />

          {/* Notifications */}
          <NotificationDrawer
            notifications={notifications}
            onMarkAllRead={handleMarkAllRead}
            onMarkRead={handleMarkRead}
            onClear={handleClearNotifications}
            onOpen={handleDrawerOpen}
          />

          {/* Sign out */}
          <button
            onClick={handleSignOut}
            title="Sign out"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 border border-gray-200 rounded-lg hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors"
          >
            <LogoutIcon className="w-3.5 h-3.5" />
            Logout
          </button>
        </div>
      </header>

      {error && (
        <div className="bg-red-50 border-b border-red-200 text-red-700 text-xs px-4 py-2 shrink-0">
          {error}
        </div>
      )}

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {/* Left column: Notifications status + Quick Actions */}
        <div style={{ width: sidebarWidth }} className="shrink-0 border-r border-gray-200 flex flex-col min-w-0">
          <SuggestionsPane
            onSuggestion={handleSuggestion}
            activeAgent={activeAgent}
            onAgentChange={setActiveAgent}
            disabled={isStreaming}
            notification={sidebarNotification}
          />
        </div>

        {/* Drag handle */}
        <div
          onMouseDown={handleDragStart}
          className="w-1.5 shrink-0 cursor-col-resize bg-transparent hover:bg-indigo-300 active:bg-indigo-400 transition-colors"
          title="Drag to resize"
        />

        <div className="flex flex-col flex-1 min-w-0">
          <ChatWindow messages={messages} onSuggestion={handleSuggestion} userName={userName} />
          <MessageInput
            onSend={handleSendMessage}
            activeAgent={activeAgent}
            onAgentChange={setActiveAgent}
            disabled={isStreaming}
            suggestion={suggestion ?? undefined}
          />
        </div>
      </div>

      {/* ── Floating toast overlay — isolated from sidebar layout ─────── */}
      <div className="fixed bottom-[100px] w-72 z-50" style={{ left: sidebarWidth + 8 }}>
        <TriggerToast notification={pendingToast} onDismiss={handleDismissToast} />
      </div>
    </div>
  );
}
