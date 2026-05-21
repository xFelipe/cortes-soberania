"""Pydantic models para Video, Clip e TriageResult."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class VideoStatus(StrEnum):
    DISCOVERED = "discovered"
    TRIAGE_METADATA_PASSED = "triage_metadata_passed"
    TRIAGE_METADATA_REJECTED = "triage_metadata_rejected"
    ON_HOLD_METADATA_PASSED = "on_hold_metadata_passed"
    TRIAGE_CAPTION_PASSED = "triage_caption_passed"
    TRIAGE_CAPTION_REJECTED = "triage_caption_rejected"
    TRIAGE_CAPTION_SKIPPED = "triage_caption_skipped"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    TRANSCRIBE_ERROR = "transcribe_error"
    TRIAGE_TRANSCRIPT_PASSED = "triage_transcript_passed"
    TRIAGE_TRANSCRIPT_REJECTED = "triage_transcript_rejected"
    APPROVED_FOR_CLIPS = "approved_for_clips"
    FINDING_CLIPS = "finding_clips"
    CLIPS_FOUND = "clips_found"
    PROCESSING_ERROR = "processing_error"


class ClipStatus(StrEnum):
    IDENTIFIED = "identified"
    EDITING = "editing"
    EDITED = "edited"
    THUMBNAIL_READY = "thumbnail_ready"
    METADATA_READY = "metadata_ready"
    UPLOADING_YOUTUBE = "uploading_youtube"
    SCHEDULED_YOUTUBE = "scheduled_youtube"
    UPLOADED_YOUTUBE = "uploaded_youtube"
    REJECTED_YOUTUBE = "rejected_youtube"
    DELETED_YOUTUBE = "deleted_youtube"
    UNSCHEDULED_YOUTUBE = "unscheduled_youtube"
    PENDING_TIKTOK_MANUAL = "pending_tiktok_manual"
    UPLOADED_TIKTOK = "uploaded_tiktok"
    PROCESSING_ERROR = "processing_error"


class TriageStage(StrEnum):
    METADATA = "metadata"
    CAPTION = "caption"
    TRANSCRIPT = "transcript"


class Video(BaseModel):
    video_id: str = Field(..., min_length=11, max_length=11)
    canal_id: str
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    published_at: str
    duration_s: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    audio_path: str | None = None
    video_path: str | None = None
    caption_path: str | None = None
    transcript_path: str | None = None
    legendas_queimadas: bool | None = None
    status: VideoStatus = VideoStatus.DISCOVERED
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    score_triage: int | None = None  # score da triagem mais avançada disponível (0-10)
    target_canal_id: str = "soberania"


class Clip(BaseModel):
    clip_id: str
    video_id: str
    start_s: float
    end_s: float
    hook: str | None = None
    payoff: str | None = None
    tema_soberania: str | None = None
    score_viral: int | None = None
    score_relevancia: int | None = None
    justificativa: str | None = None
    clip_path_vertical: str | None = None
    clip_path_horizontal: str | None = None
    thumb_path: str | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    youtube_id: str | None = None
    youtube_id_horizontal: str | None = None
    tiktok_id: str | None = None
    youtube_publish_at: str | None = None
    youtube_publish_at_horizontal: str | None = None
    render_vertical: bool = True
    render_horizontal: bool = True
    # sync de status e métricas (migration 005)
    youtube_privacy_status: str | None = None
    youtube_upload_status: str | None = None
    youtube_rejection_reason: str | None = None
    youtube_actual_published_at: str | None = None
    youtube_last_synced_at: str | None = None
    youtube_view_count: int | None = None
    youtube_like_count: int | None = None
    youtube_comment_count: int | None = None
    youtube_privacy_status_horizontal: str | None = None
    youtube_upload_status_horizontal: str | None = None
    youtube_view_count_horizontal: int | None = None
    youtube_like_count_horizontal: int | None = None
    youtube_comment_count_horizontal: int | None = None
    target_canal_id: str = "soberania"
    status: ClipStatus = ClipStatus.IDENTIFIED
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def duracao_s(self) -> float:
        return self.end_s - self.start_s


class TriageResult(BaseModel):
    video_id: str
    stage: TriageStage
    score: int = Field(..., ge=0, le=10)
    is_relevant: bool
    themes_detected: list[str] = Field(default_factory=list)
    rationale: str = ""
    raw_response: str = ""
    model_used: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None


class ClipCandidate(BaseModel):
    """Resultado bruto do LLM para identificação de cortes."""

    start_s: float
    end_s: float
    hook: str
    payoff: str
    score_viral: int = Field(..., ge=0, le=10)
    score_relevancia: int = Field(..., ge=0, le=10)
    tema_soberania: str
    justificativa: str
