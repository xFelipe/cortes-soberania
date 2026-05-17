"""Pydantic models para Video, Clip e TriageResult."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VideoStatus = Literal[
    "discovered",
    "triage_metadata_passed",
    "triage_metadata_rejected",
    "on_hold_metadata_passed",
    "triage_caption_passed",
    "triage_caption_rejected",
    "triage_caption_skipped",
    "downloading",
    "downloaded",
    "transcribing",
    "transcribed",
    "transcribe_error",
    "triage_transcript_passed",
    "triage_transcript_rejected",
    "finding_clips",
    "clips_found",
    "processing_error",
]

ClipStatus = Literal[
    "identified",
    "editing",
    "edited",
    "thumbnail_ready",
    "metadata_ready",
    "scheduled_youtube",
    "uploaded_youtube",
    "pending_tiktok_manual",
    "uploaded_tiktok",
    "processing_error",
]

TriageStage = Literal["metadata", "caption", "transcript"]


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
    status: VideoStatus = "discovered"
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


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
    status: ClipStatus = "identified"
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
