const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://127.0.0.1:8000";
const XDG_TOKEN_PATH = `${import.meta.env.HOME ?? ""}/config/canal-soberania/.api_token`;

async function getToken(): Promise<string> {
  try {
    const { readTextFile } = await import("@tauri-apps/plugin-fs");
    const raw = await readTextFile(XDG_TOKEN_PATH);
    return raw.trim();
  } catch {
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

// ── Types ─────────────────────────────────────────────────────────────────────

export interface StatsSummary {
  [status: string]: number;
}

export interface StatsCosts {
  total_usd: number;
}

export interface Video {
  video_id: string;
  canal_id: string;
  title: string;
  description: string | null;
  tags: string[];
  published_at: string;
  duration_s: number | null;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  status: string;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
  score_triage: number | null;
}

export interface Clip {
  clip_id: string;
  video_id: string;
  start_s: number;
  end_s: number;
  hook: string | null;
  payoff: string | null;
  tema_soberania: string | null;
  score_viral: number | null;
  score_relevancia: number | null;
  title: string | null;
  description: string | null;
  tags: string[];
  youtube_id: string | null;
  thumb_path: string | null;
  youtube_view_count: number | null;
  youtube_like_count: number | null;
  status: string;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface FaceCropData {
  crop_x: number;
  crop_width: number;
  source_width: number;
  source_height: number;
}

export interface ClipPatch {
  hook?: string | null;
  payoff?: string | null;
  title?: string | null;
  description?: string | null;
  tags?: string[];
  youtube_publish_at?: string | null;
  render_vertical?: boolean;
  render_horizontal?: boolean;
  score_viral?: number | null;
}

export interface InboxItem {
  type: "clip" | "video";
  priority: number;
  clip_id?: string;
  video_id?: string;
  hook?: string;
  title?: string;
  status?: string;
  canal_id?: string;
  score_viral?: number;
  start_s?: number;
  end_s?: number;
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
      request<{ status: string; stage: string }>(`/stages/${name}/run`, { method: "POST" }),
    cancel: () =>
      request<{ status: string }>("/pipeline/cancel", { method: "POST" }),
    reset: () =>
      request<{ reset_videos: number; reset_clips: number }>("/pipeline/reset", { method: "POST" }),
  },
  videos: {
    list: (params?: { status?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.status) qs.set("status", params.status);
      if (params?.limit) qs.set("limit", String(params.limit));
      const q = qs.toString();
      return request<Video[]>(`/videos${q ? `?${q}` : ""}`);
    },
    approve: (video_id: string) =>
      request<{ status: string; video_id: string }>(`/videos/${video_id}/approve`, { method: "POST" }),
    reject: (video_id: string) =>
      request<{ status: string; video_id: string }>(`/videos/${video_id}/reject`, { method: "POST" }),
  },
  clips: {
    list: (params?: { status?: string; video_id?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.status) qs.set("status", params.status);
      if (params?.video_id) qs.set("video_id", params.video_id);
      if (params?.limit) qs.set("limit", String(params.limit));
      const q = qs.toString();
      return request<Clip[]>(`/clips${q ? `?${q}` : ""}`);
    },
    get: (clip_id: string) => request<Clip>(`/clips/${clip_id}`),
    approve: (clip_id: string) =>
      request<{ status: string; clip_id: string }>(`/clips/${clip_id}/approve`, { method: "POST" }),
    reject: (clip_id: string) =>
      request<{ status: string; clip_id: string }>(`/clips/${clip_id}/reject`, { method: "POST" }),
    discard: (clip_id: string) =>
      request<{ status: string; clip_id: string }>(`/clips/${clip_id}`, { method: "DELETE" }),
    patch: (clip_id: string, data: ClipPatch) =>
      request<{ status: string; clip_id: string }>(`/clips/${clip_id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    trim: (clip_id: string, start_s: number, end_s: number) =>
      request<{ status: string; clip_id: string; start_s: number; end_s: number }>(
        `/clips/${clip_id}/trim`,
        { method: "POST", body: JSON.stringify({ start_s, end_s }) }
      ),
    faceCrop: (clip_id: string) =>
      request<FaceCropData>(`/clips/${clip_id}/face-crop`),
    sourceVideoUrl: (clip_id: string) => `${API_URL}/clips/${clip_id}/source-video`,
  },
};

export { API_URL, getToken };
