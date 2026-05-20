// STATUS_META — mapeamento centralizado de status → label PT + cor + ativo
// Fonte: gui/widgets/video_table.py, gui/windows/main_window.py

export type VideoStatus =
  | "discovered"
  | "triage_metadata_passed"
  | "triage_metadata_rejected"
  | "on_hold_metadata_passed"
  | "triage_caption_passed"
  | "triage_caption_rejected"
  | "triage_caption_skipped"
  | "downloading"
  | "downloaded"
  | "transcribing"
  | "transcribed"
  | "transcribe_error"
  | "triage_transcript_passed"
  | "triage_transcript_rejected"
  | "approved_for_clips"
  | "finding_clips"
  | "clips_found"
  | "processing_error";

export type ClipStatus =
  | "identified"
  | "editing"
  | "edited"
  | "thumbnail_ready"
  | "metadata_ready"
  | "uploading_youtube"
  | "scheduled_youtube"
  | "uploaded_youtube"
  | "rejected_youtube"
  | "deleted_youtube"
  | "unscheduled_youtube"
  | "pending_tiktok_manual"
  | "uploaded_tiktok"
  | "processing_error";

export interface VideoStatusMeta {
  label: string;
  color: string;
  active: boolean;
}

export interface ClipStatusMeta {
  label: string;
  color: string;
}

export const VIDEO_STATUS_META: Record<VideoStatus, VideoStatusMeta> = {
  discovered: { label: "Descoberto", color: "#555555", active: false },
  triage_metadata_passed: { label: "Triagem meta ✓", color: "#2e7d32", active: false },
  triage_metadata_rejected: { label: "Triagem meta ✗", color: "#b71c1c", active: false },
  on_hold_metadata_passed: { label: "Aguarda (meta)", color: "#6a1e8a", active: false },
  triage_caption_passed: { label: "Triagem caption ✓", color: "#1b5e20", active: false },
  triage_caption_rejected: { label: "Triagem caption ✗", color: "#c62828", active: false },
  triage_caption_skipped: { label: "Caption pulada", color: "#4e342e", active: false },
  downloading: { label: "Baixando…", color: "#f57f17", active: true },
  downloaded: { label: "Baixado", color: "#33691e", active: false },
  transcribing: { label: "Transcrevendo…", color: "#e65100", active: true },
  transcribed: { label: "Transcrito", color: "#1a237e", active: false },
  transcribe_error: { label: "Erro transcrição", color: "#b71c1c", active: false },
  triage_transcript_passed: { label: "Triagem transcript ✓", color: "#e65100", active: false },
  triage_transcript_rejected: { label: "Triagem transcript ✗", color: "#880e4f", active: false },
  approved_for_clips: { label: "Aprovado p/ cortes", color: "#004d40", active: false },
  finding_clips: { label: "Buscando cortes…", color: "#4a148c", active: true },
  clips_found: { label: "Cortes encontrados", color: "#1565c0", active: false },
  processing_error: { label: "Erro", color: "#d50000", active: false },
};

export const CLIP_STATUS_META: Record<ClipStatus, ClipStatusMeta> = {
  identified: { label: "Identificado", color: "#555555" },
  editing: { label: "Editando…", color: "#f57f17" },
  edited: { label: "Editado", color: "#33691e" },
  thumbnail_ready: { label: "Thumb pronta", color: "#1565c0" },
  metadata_ready: { label: "Revisão pendente", color: "#e65100" },
  uploading_youtube: { label: "Subindo YT…", color: "#f57f17" },
  scheduled_youtube: { label: "Agendado YT", color: "#004d40" },
  uploaded_youtube: { label: "No YouTube ✓", color: "#1b5e20" },
  rejected_youtube: { label: "Rejeitado YT", color: "#880e4f" },
  deleted_youtube: { label: "Deletado YT", color: "#555555" },
  unscheduled_youtube: { label: "Desagendado YT", color: "#4e342e" },
  pending_tiktok_manual: { label: "Fila TikTok", color: "#e65100" },
  uploaded_tiktok: { label: "No TikTok ✓", color: "#880e4f" },
  processing_error: { label: "Erro", color: "#d50000" },
};

export const ACTIVE_VIDEO_STATUSES = new Set<VideoStatus>(
  (Object.entries(VIDEO_STATUS_META) as [VideoStatus, VideoStatusMeta][])
    .filter(([, m]) => m.active)
    .map(([s]) => s)
);

// Mapeamento stage → statuses que indicam "pendente naquele stage"
// Usado na página Operação para exibir contagem de pendentes por stage.
export const STAGE_PENDING_STATUSES: Record<string, string[]> = {
  discover: [],
  triage_metadata: ["discovered"],
  triage_caption: ["triage_metadata_passed", "on_hold_metadata_passed"],
  download: ["triage_caption_passed", "triage_caption_skipped"],
  transcribe: ["downloaded"],
  triage_transcript: ["transcribed"],
  find_clips: ["approved_for_clips"],
  edit: ["identified"],
  thumbnail: ["edited"],
  generate_metadata: ["thumbnail_ready"],
  upload_youtube: ["metadata_ready", "unscheduled_youtube"],
  upload_tiktok: ["pending_tiktok_manual"],
  sync_youtube: ["scheduled_youtube", "uploaded_youtube"],
};

export function stagePendingCount(
  summary: Record<string, number>,
  stageName: string
): number {
  const statuses = STAGE_PENDING_STATUSES[stageName] ?? [];
  return statuses.reduce((acc, s) => acc + (summary[s] ?? 0), 0);
}
