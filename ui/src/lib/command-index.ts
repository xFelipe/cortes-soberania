import { useSyncExternalStore } from "react";
import { api } from "./api";
import type { SSEEvent } from "./sse";

// ── Tipos mínimos do índice ───────────────────────────────────────────────────

export interface IndexVideo {
  id: string;
  title: string;
  canal_id: string;
  status: string;
}

export interface IndexClip {
  id: string;
  hook: string | null;
  title: string | null;
  video_id: string;
  status: string;
  score_viral: number | null;
}

export interface IndexCanal {
  id: string;
  nome: string;
  handle: string;
}

interface IndexState {
  videos: IndexVideo[];
  clips: IndexClip[];
  canais: IndexCanal[];
}

// ── Store module-level ────────────────────────────────────────────────────────

let state: IndexState = { videos: [], clips: [], canais: [] };
let seeded = false;
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((cb) => cb());
}

function setState(next: Partial<IndexState>): void {
  state = { ...state, ...next };
  notify();
}

// ── Seed ──────────────────────────────────────────────────────────────────────

export async function seedIndex(): Promise<void> {
  if (seeded) return;
  seeded = true;
  try {
    const [videos, clips, canais] = await Promise.all([
      api.videos.list({ limit: 500 }),
      api.clips.list({ limit: 500 }),
      api.canais.list(),
    ]);
    setState({
      videos: videos.map((v) => ({ id: v.video_id, title: v.title, canal_id: v.canal_id, status: v.status })),
      clips: clips.map((c) => ({ id: c.clip_id, hook: c.hook, title: c.title, video_id: c.video_id, status: c.status, score_viral: c.score_viral ?? null })),
      canais: canais.map((c) => ({ id: c.id, nome: c.nome, handle: c.handle })),
    });
  } catch {
    seeded = false; // allow retry on next mount
  }
}

// ── Patch incremental via SSE ─────────────────────────────────────────────────

export function applyEvent(event: SSEEvent): void {
  const { type, data } = event;
  const p = data as Record<string, unknown>;

  if (type === "clip_discarded") {
    const id = p.clip_id as string | undefined;
    if (id) setState({ clips: state.clips.filter((c) => c.id !== id) });
    return;
  }

  if (type === "clip_approved" || type === "clip_rejected") {
    const id = p.clip_id as string | undefined;
    if (!id) return;
    const newStatus = p.new_status as string | undefined;
    if (newStatus) {
      setState({ clips: state.clips.map((c) => c.id === id ? { ...c, status: newStatus } : c) });
    } else {
      void api.clips.get(id).then((c) => {
        setState({
          clips: state.clips.map((x) =>
            x.id === id ? { ...x, status: c.status, hook: c.hook, title: c.title, score_viral: c.score_viral ?? null } : x
          ),
        });
      });
    }
    return;
  }

  if (type === "clip_text_updated" || type === "clip_trim_updated") {
    const id = p.clip_id as string | undefined;
    if (!id) return;
    void api.clips.get(id).then((c) => {
      setState({
        clips: state.clips.map((x) =>
          x.id === id ? { ...x, hook: c.hook, title: c.title, status: c.status, score_viral: c.score_viral ?? null } : x
        ),
      });
    });
    return;
  }

  if (type === "video_approved" || type === "video_rejected") {
    const id = p.video_id as string | undefined;
    if (!id) return;
    const newStatus = p.new_status as string | undefined;
    if (newStatus) {
      setState({ videos: state.videos.map((v) => v.id === id ? { ...v, status: newStatus } : v) });
    }
    return;
  }

  if (type === "video_added_manually") {
    const id = p.video_id as string | undefined;
    const title = (p.title as string | undefined) ?? "";
    if (id) {
      const exists = state.videos.some((v) => v.id === id);
      if (!exists) setState({ videos: [{ id, title, canal_id: "", status: "discovered" }, ...state.videos] });
    }
    return;
  }

  if (type === "canal_deleted") {
    const id = p.canal_id as string | undefined;
    if (id) setState({ canais: state.canais.filter((c) => c.id !== id) });
    return;
  }

  if (type === "canal_upserted" || type === "canal_toggled") {
    void api.canais.list().then((canais) => {
      setState({ canais: canais.map((c) => ({ id: c.id, nome: c.nome, handle: c.handle })) });
    });
  }
}

// ── useSyncExternalStore hook ─────────────────────────────────────────────────

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function getSnapshot(): IndexState {
  return state;
}

export function useCommandIndex(): IndexState {
  return useSyncExternalStore(subscribe, getSnapshot);
}
