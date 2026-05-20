import { useEffect, useState, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_URL, getToken } from "./api";

type SSEStatus = "connecting" | "open" | "closed";

export interface SSEEvent {
  type: string;
  data: unknown;
}

export function useSSE(onEvent?: (event: SSEEvent) => void) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<SSEStatus>("connecting");
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    async function connect() {
      if (cancelled) return;
      const token = await getToken();
      es = new EventSource(`${API_URL}/events?token=${encodeURIComponent(token)}`);

      es.onopen = () => setStatus("open");

      es.onerror = () => {
        setStatus("closed");
        es?.close();
        if (!cancelled) {
          retryTimer = setTimeout(connect, 3_000);
        }
      };

      es.onmessage = (e: MessageEvent<string>) => {
        try {
          const parsed = JSON.parse(e.data) as { type?: string; payload?: Record<string, unknown> };
          const eventType = parsed.type ?? "unknown";
          const payload = parsed.payload ?? {};

          if (onEventRef.current) {
            onEventRef.current({ type: eventType, data: payload });
          }

          if (eventType.includes("clip")) {
            void queryClient.invalidateQueries({ queryKey: ["clips"] });
            void queryClient.invalidateQueries({ queryKey: ["inbox"] });
          }
          if (eventType.includes("video")) {
            void queryClient.invalidateQueries({ queryKey: ["videos"] });
            void queryClient.invalidateQueries({ queryKey: ["inbox"] });
          }
          void queryClient.invalidateQueries({ queryKey: ["stats"] });
        } catch {
          // ignore malformed heartbeat / non-JSON lines
        }
      };
    }

    void connect();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      es?.close();
    };
  }, [queryClient]);

  return status;
}
