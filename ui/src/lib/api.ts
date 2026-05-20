const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://127.0.0.1:8000";
const XDG_TOKEN_PATH = `${import.meta.env.HOME ?? ""}/config/canal-soberania/.api_token`;

async function getToken(): Promise<string> {
  try {
    // Tauri environment: read from XDG config path
    const { readTextFile } = await import("@tauri-apps/plugin-fs");
    const raw = await readTextFile(XDG_TOKEN_PATH);
    return raw.trim();
  } catch {
    // Browser / dev fallback: token in localStorage (set manually for testing)
    return localStorage.getItem("api_token") ?? "";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// ── Types (minimal subset used in Onda 3) ────────────────────────────────────

export interface StatsSummary {
  [status: string]: number;
}

export interface StatsCosts {
  total_usd: number;
}

export interface InboxItem {
  type: "clip" | "video";
  priority: number;
  clip_id?: string;
  video_id?: string;
  hook?: string;
  title?: string;
  status?: string;
}

export interface InboxResponse {
  items: InboxItem[];
  total: number;
}

// ── API surface ───────────────────────────────────────────────────────────────

export const api = {
  stats: {
    summary: () => request<StatsSummary>("/stats/summary"),
    costs: () => request<StatsCosts>("/stats/costs"),
  },
  inbox: {
    get: () => request<InboxResponse>("/inbox"),
  },
  stages: {
    run: (name: string) =>
      request<{ status: string; stage: string }>(`/stages/${name}/run`, {
        method: "POST",
      }),
    cancel: () =>
      request<{ status: string }>("/pipeline/cancel", { method: "POST" }),
    reset: () => request<{ reset_videos: number; reset_clips: number }>("/pipeline/reset", { method: "POST" }),
  },
  videos: {
    list: (params?: { status?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.status) qs.set("status", params.status);
      if (params?.limit) qs.set("limit", String(params.limit));
      const q = qs.toString();
      return request<unknown[]>(`/videos${q ? `?${q}` : ""}`);
    },
  },
  clips: {
    list: (params?: { status?: string; video_id?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.status) qs.set("status", params.status);
      if (params?.video_id) qs.set("video_id", params.video_id);
      if (params?.limit) qs.set("limit", String(params.limit));
      const q = qs.toString();
      return request<unknown[]>(`/clips${q ? `?${q}` : ""}`);
    },
  },
};

export { API_URL, getToken };
