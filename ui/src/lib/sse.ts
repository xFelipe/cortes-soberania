import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_URL, getToken } from "./api";

type SSEStatus = "connecting" | "open" | "closed";

export function useSSE() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<SSEStatus>("connecting");

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
          const event = JSON.parse(e.data) as { event_type?: string };
          if (event.event_type?.includes("clip")) {
            void queryClient.invalidateQueries({ queryKey: ["clips"] });
            void queryClient.invalidateQueries({ queryKey: ["inbox"] });
          }
          if (event.event_type?.includes("video")) {
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
