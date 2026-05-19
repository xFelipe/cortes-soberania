"""State machine para os ciclos de vida de Video e Clip."""

from __future__ import annotations

from canal_soberania.logger import logger
from canal_soberania.models import ClipStatus, VideoStatus

# ---------------------------------------------------------------------------
# Transições válidas de Video
# ---------------------------------------------------------------------------

VS = VideoStatus

VIDEO_TRANSITIONS: dict[VideoStatus, list[VideoStatus]] = {
    VS.DISCOVERED: [VS.TRIAGE_METADATA_PASSED, VS.TRIAGE_METADATA_REJECTED, VS.ON_HOLD_METADATA_PASSED, VS.PROCESSING_ERROR],
    VS.TRIAGE_METADATA_PASSED: [VS.TRIAGE_CAPTION_PASSED, VS.TRIAGE_CAPTION_REJECTED, VS.TRIAGE_CAPTION_SKIPPED, VS.ON_HOLD_METADATA_PASSED, VS.PROCESSING_ERROR],
    VS.ON_HOLD_METADATA_PASSED: [VS.TRIAGE_CAPTION_PASSED, VS.PROCESSING_ERROR],
    VS.TRIAGE_METADATA_REJECTED: [],
    VS.TRIAGE_CAPTION_PASSED: [VS.DOWNLOADING, VS.PROCESSING_ERROR],
    VS.TRIAGE_CAPTION_REJECTED: [],
    VS.TRIAGE_CAPTION_SKIPPED: [VS.DOWNLOADING, VS.PROCESSING_ERROR],
    VS.DOWNLOADING: [VS.DOWNLOADED, VS.DISCOVERED, VS.PROCESSING_ERROR],  # discovered = retry
    VS.DOWNLOADED: [VS.TRANSCRIBING, VS.PROCESSING_ERROR],
    VS.TRANSCRIBING: [VS.TRANSCRIBED, VS.TRANSCRIBE_ERROR, VS.PROCESSING_ERROR],
    VS.TRANSCRIBE_ERROR: [VS.TRANSCRIBING],  # permite retry
    VS.TRANSCRIBED: [VS.TRIAGE_TRANSCRIPT_PASSED, VS.TRIAGE_TRANSCRIPT_REJECTED, VS.PROCESSING_ERROR],
    VS.TRIAGE_TRANSCRIPT_PASSED: [VS.APPROVED_FOR_CLIPS, VS.PROCESSING_ERROR],
    VS.TRIAGE_TRANSCRIPT_REJECTED: [VS.APPROVED_FOR_CLIPS],  # override manual da rejeição
    VS.APPROVED_FOR_CLIPS: [VS.FINDING_CLIPS, VS.PROCESSING_ERROR],
    VS.FINDING_CLIPS: [VS.CLIPS_FOUND, VS.PROCESSING_ERROR],
    VS.CLIPS_FOUND: [],
    VS.PROCESSING_ERROR: [VS.DISCOVERED],  # reset manual para reprocessar
}

# ---------------------------------------------------------------------------
# Transições válidas de Clip
# ---------------------------------------------------------------------------

CS = ClipStatus

CLIP_TRANSITIONS: dict[ClipStatus, list[ClipStatus]] = {
    CS.IDENTIFIED: [CS.EDITING, CS.PROCESSING_ERROR],
    CS.EDITING: [CS.EDITED, CS.IDENTIFIED, CS.PROCESSING_ERROR],  # identified = retry
    CS.EDITED: [CS.THUMBNAIL_READY, CS.PROCESSING_ERROR],
    CS.THUMBNAIL_READY: [CS.METADATA_READY, CS.PROCESSING_ERROR],
    CS.METADATA_READY: [CS.UPLOADING_YOUTUBE, CS.SCHEDULED_YOUTUBE, CS.PENDING_TIKTOK_MANUAL, CS.PROCESSING_ERROR],
    CS.UPLOADING_YOUTUBE: [CS.SCHEDULED_YOUTUBE, CS.METADATA_READY, CS.PROCESSING_ERROR],
    CS.SCHEDULED_YOUTUBE: [
        CS.UPLOADED_YOUTUBE,      # publicou de verdade
        CS.REJECTED_YOUTUBE,      # YouTube rejeitou (copyright/spam/etc.)
        CS.DELETED_YOUTUBE,       # vídeo removido
        CS.UNSCHEDULED_YOUTUBE,   # publishAt foi removido pelo dono
        CS.PROCESSING_ERROR,
    ],
    CS.UPLOADED_YOUTUBE: [CS.DELETED_YOUTUBE, CS.PENDING_TIKTOK_MANUAL],
    CS.REJECTED_YOUTUBE: [CS.IDENTIFIED, CS.PROCESSING_ERROR],   # re-editar ou descartar
    CS.DELETED_YOUTUBE: [CS.IDENTIFIED],                         # re-fazer do zero
    CS.UNSCHEDULED_YOUTUBE: [CS.SCHEDULED_YOUTUBE, CS.METADATA_READY],  # reagendar ou rever
    CS.PENDING_TIKTOK_MANUAL: [CS.UPLOADED_TIKTOK],
    CS.UPLOADED_TIKTOK: [],
    CS.PROCESSING_ERROR: [CS.IDENTIFIED],  # reset manual
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
