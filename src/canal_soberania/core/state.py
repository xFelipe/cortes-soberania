"""State machine para os ciclos de vida de Video e Clip."""

from __future__ import annotations

from canal_soberania.logger import logger
from canal_soberania.models import ClipStatus, VideoStatus

# ---------------------------------------------------------------------------
# Transições válidas de Video
# ---------------------------------------------------------------------------

VIDEO_TRANSITIONS: dict[VideoStatus, list[VideoStatus]] = {
    "discovered": ["triage_metadata_passed", "triage_metadata_rejected", "on_hold_metadata_passed", "processing_error"],
    "triage_metadata_passed": ["triage_caption_passed", "triage_caption_rejected", "triage_caption_skipped", "on_hold_metadata_passed", "processing_error"],
    "on_hold_metadata_passed": ["triage_caption_passed", "processing_error"],
    "triage_metadata_rejected": [],
    "triage_caption_passed": ["downloading", "processing_error"],
    "triage_caption_rejected": [],
    "triage_caption_skipped": ["downloading", "processing_error"],
    "downloading": ["downloaded", "discovered", "processing_error"],  # discovered = retry
    "downloaded": ["transcribing", "processing_error"],
    "transcribing": ["transcribed", "transcribe_error", "processing_error"],
    "transcribe_error": ["transcribing"],  # permite retry
    "transcribed": ["triage_transcript_passed", "triage_transcript_rejected", "processing_error"],
    "triage_transcript_passed": ["approved_for_clips", "processing_error"],
    "triage_transcript_rejected": ["approved_for_clips"],  # override manual da rejeição
    "approved_for_clips": ["finding_clips", "processing_error"],
    "finding_clips": ["clips_found", "processing_error"],
    "clips_found": [],
    "processing_error": ["discovered"],  # reset manual para reprocessar
}

# ---------------------------------------------------------------------------
# Transições válidas de Clip
# ---------------------------------------------------------------------------

CLIP_TRANSITIONS: dict[ClipStatus, list[ClipStatus]] = {
    "identified": ["editing", "processing_error"],
    "editing": ["edited", "identified", "processing_error"],  # identified = retry
    "edited": ["thumbnail_ready", "processing_error"],
    "thumbnail_ready": ["metadata_ready", "processing_error"],
    "metadata_ready": ["scheduled_youtube", "pending_tiktok_manual", "processing_error"],
    "scheduled_youtube": ["uploaded_youtube", "processing_error"],
    "uploaded_youtube": ["pending_tiktok_manual"],
    "pending_tiktok_manual": ["uploaded_tiktok"],
    "uploaded_tiktok": [],
    "processing_error": ["identified"],  # reset manual
}


class InvalidTransitionError(Exception):
    """Tentativa de transição de estado inválida."""


class VideoStateMachine:
    @staticmethod
    def transition(video_id: str, current: VideoStatus, new: VideoStatus) -> None:
        allowed = VIDEO_TRANSITIONS.get(current, [])
        if new not in allowed:
            raise InvalidTransitionError(
                f"Video {video_id}: transição inválida {current!r} → {new!r}. "
                f"Permitidas: {allowed}"
            )
        logger.debug("Video {} | {} → {}", video_id, current, new)

    @staticmethod
    def can_transition(current: VideoStatus, new: VideoStatus) -> bool:
        return new in VIDEO_TRANSITIONS.get(current, [])


class ClipStateMachine:
    @staticmethod
    def transition(clip_id: str, current: ClipStatus, new: ClipStatus) -> None:
        allowed = CLIP_TRANSITIONS.get(current, [])
        if new not in allowed:
            raise InvalidTransitionError(
                f"Clip {clip_id}: transição inválida {current!r} → {new!r}. "
                f"Permitidas: {allowed}"
            )
        logger.debug("Clip {} | {} → {}", clip_id, current, new)

    @staticmethod
    def can_transition(current: ClipStatus, new: ClipStatus) -> bool:
        return new in CLIP_TRANSITIONS.get(current, [])
