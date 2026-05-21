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

export interface StatsCostDetail {
  date: string;
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  requests: number;
  cost_usd: number;
}

export interface StatsByCanal {
  canal_id: string;
  total_videos: number;
  videos_aprovados: number;
  clips_gerados: number;
  clips_publicados: number;
}

export interface StatsThroughput {
  semana: string;
  videos_descobertos: number;
  clips_criados: number;
  clips_publicados: number;
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
  target_canal_id: string;
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
  target_canal_id: string;
}

export interface OutputCanal {
  id: string;
  nome: string;
  tema: string;
  fontes: string[];
  criteria_path: string;
  branding_dir: string;
  youtube_channel_id: string;
  youtube_token_path: string;
  ativo: boolean;
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

export interface Canal {
  id: string;
  nome: string;
  handle: string;
  channel_url: string;
  tema_primario: string;
  peso: number;
  auto_publish: boolean;
  tolerancia_cortes: string;
  nota: string;
  ativo: boolean;
}

export interface DiscoverAdhocParams {
  channel_url_or_handle: string;
  persist?: boolean;
  janela_dias?: number | null;
  max_videos?: number | null;
}

export type ConfigValues = Record<string, string | number | boolean>;

// ── API surface ───────────────────────────────────────────────────────────────

export const api = {
  stats: {
    summary: () => request<StatsSummary>("/stats/summary"),
    costs: () => request<StatsCosts>("/stats/costs"),
    costsDetail: () => request<StatsCostDetail[]>("/stats/costs/detail"),
    byCanal: () => request<StatsByCanal[]>("/stats/by-canal"),
    throughput: () => request<StatsThroughput[]>("/stats/throughput"),
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
  discover: {
    adhoc: (params: DiscoverAdhocParams) =>
      request<{ status: string; handle: string }>("/discover/adhoc", {
        method: "POST",
        body: JSON.stringify(params),
      }),
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
  canais: {
    list: () => request<Canal[]>("/canais"),
    create: (canal: Canal) =>
      request<Canal>("/canais", { method: "POST", body: JSON.stringify(canal) }),
    update: (id: string, canal: Canal) =>
      request<Canal>(`/canais/${id}`, { method: "PUT", body: JSON.stringify(canal) }),
    toggleAtivo: (id: string, ativo: boolean) =>
      request<{ canal_id: string; ativo: boolean }>(`/canais/${id}/ativo`, {
        method: "PATCH",
        body: JSON.stringify({ ativo }),
      }),
    remove: (id: string) =>
      request<{ status: string; canal_id: string }>(`/canais/${id}`, { method: "DELETE" }),
  },
  config: {
    get: () => request<ConfigValues>("/config"),
    put: (patch: ConfigValues) =>
      request<{ status: string; restart_required: boolean; updated: string[] }>("/config", {
        method: "PUT",
        body: JSON.stringify(patch),
      }),
  },
  pipeline: {
    pause: () => request<{ paused: true }>("/pipeline/pause", { method: "POST" }),
    resume: () => request<{ paused: false }>("/pipeline/resume", { method: "POST" }),
    loopState: () => request<{ paused: boolean }>("/pipeline/loop-state"),
  },
  outputCanais: {
    list: () => request<OutputCanal[]>("/output-canais"),
    get: (id: string) => request<OutputCanal>(`/output-canais/${id}`),
    create: (canal: OutputCanal) =>
      request<OutputCanal>("/output-canais", { method: "POST", body: JSON.stringify(canal) }),
    update: (id: string, canal: OutputCanal) =>
      request<OutputCanal>(`/output-canais/${id}`, { method: "PUT", body: JSON.stringify(canal) }),
    remove: (id: string) =>
      request<{ status: string; canal_id: string }>(`/output-canais/${id}`, { method: "DELETE" }),
    getFontes: (id: string) => request<string[]>(`/output-canais/${id}/fontes`),
    setFontes: (id: string, fontes: string[]) =>
      request<string[]>(`/output-canais/${id}/fontes`, { method: "PUT", body: JSON.stringify(fontes) }),
  },
};

export { API_URL, getToken };
