"use client";

import { useEffect, useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import { NotificationItem } from "@/lib/types";
import { triggerStreamUrl } from "@/lib/api";

interface Props {
  userEmail: string;
  onNotification: (item: NotificationItem) => void;
}

/** Headless SSE consumer — connects to the trigger stream and calls
 *  onNotification for every agent_complete or trigger event. No UI rendered. */
export function NotificationListener({ userEmail, onNotification }: Props) {
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!userEmail) return;

    const es = new EventSource(triggerStreamUrl(userEmail));
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        const now = Date.now();
        const time = new Date(now).toLocaleTimeString(undefined, {
          hour: "2-digit",
          minute: "2-digit",
        });

        if (data.type === "agent_complete") {
          onNotification({
            id: uuidv4(),
            type: "agent_complete",
            icon: data.processing ? "⏳" : (data.is_error ? "⚠️" : "📋"),
            title: data.title ?? "Agent complete",
            timestamp: data.timestamp || time,
            createdAt: now,
            read: false,
            body: data.body ?? "",
            draft_subject: data.draft_subject ?? "",
            email_count: data.email_count ?? 0,
            is_error: data.is_error ?? false,
            is_processing: data.processing === true,
            inclusion_rule: data.inclusion_rule ?? "",
            exclusion_rule: data.exclusion_rule ?? "",
            mode: data.mode ?? "",
          });
          return;
        }

        if (data.type !== "trigger") return;

        onNotification({
          id: uuidv4(),
          type: "trigger",
          icon: data.icon ?? "🔔",
          title: data.label ?? data.trigger_name ?? "Trigger",
          timestamp: time,
          createdAt: now,
          read: false,
          trigger_name: data.trigger_name,
          payload: data.payload ?? {},
        });
      } catch {
        // malformed event — ignore
      }
    };

    es.onerror = () => {};

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [userEmail, onNotification]);

  return null;
}
