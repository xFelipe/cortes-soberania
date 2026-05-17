"""PipelineService — ponto de entrada único para CLI e futuras UIs (PySide6, FastAPI)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from canal_soberania.config import Settings
from canal_soberania.core.events import EventBus, PipelineEvent
from canal_soberania.core.repositories import ClipRepository, VideoRepository
from canal_soberania.core.stage import JobContext
from canal_soberania.core.state import ClipStateMachine, VideoStateMachine
from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus


class PipelineService:
    """Orquestra os stages do pipeline e expõe queries para a camada de apresentação.

    Recebe dependências por injeção no construtor — nenhum import de GUI ou HTTP
    dentro desta classe. Os repositórios têm padrão Sqlite; em testes, injete
    InMemoryVideoRepository / InMemoryClipRepository.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings,
        paths: dict[str, Path],
        video_repo: VideoRepository | None = None,
        clip_repo: ClipRepository | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._conn = conn
        self._settings = settings
        self._paths = paths
        self._bus = event_bus or EventBus()

        if video_repo is None:
            from canal_soberania.repositories.sqlite import SqliteVideoRepository
            video_repo = SqliteVideoRepository(conn)
        if clip_repo is None:
            from canal_soberania.repositories.sqlite import SqliteClipRepository
            clip_repo = SqliteClipRepository(conn)

        self._video_repo = video_repo
        self._clip_repo = clip_repo
        self._cancel_event = threading.Event()

    @property
    def event_bus(self) -> EventBus:
        return self._bus

    def cancel(self) -> None:
        """Sinaliza ao pipeline para parar na próxima oportunidade."""
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        """Limpa o sinal de cancelamento para permitir novos runs."""
        self._cancel_event.clear()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_status_summary(self) -> dict[str, int]:
        return self._video_repo.status_summary()

    def get_monthly_cost(self) -> float:
        return self._video_repo.monthly_cost()

    def get_video(self, video_id: str) -> Video | None:
        return self._video_repo.get(video_id)

    def get_videos(self, status: VideoStatus | None = None) -> list[Video]:
        if status is None:
            return self._video_repo.get_all()
        return self._video_repo.get_by_status(status)

    def get_clips(self, status: ClipStatus | None = None) -> list[Clip]:
        if status is None:
            return self._clip_repo.get_all()
        return self._clip_repo.get_by_status(status)

    # ------------------------------------------------------------------
    # State machine helpers (para a UI acionar transições manuais)
    # ------------------------------------------------------------------

    def transition_video(self, video_id: str, current: VideoStatus, new: VideoStatus) -> None:
        """Valida e loga transição de estado de um vídeo. Não persiste — usa db direto."""
        VideoStateMachine.transition(video_id, current, new)

    def transition_clip(self, clip_id: str, current: ClipStatus, new: ClipStatus) -> None:
        """Valida e loga transição de estado de um clipe. Não persiste — usa db direto."""
        ClipStateMachine.transition(clip_id, current, new)

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    def _run_stage(self, stage_name: str, stage_fn: Any, dry_run: bool) -> None:
        if self._cancel_event.is_set():
            self._bus.publish(PipelineEvent("stage_cancelled", {"stage": stage_name}))
            return

        from canal_soberania.stages.wrappers import get_stage
        try:
            stage = get_stage(stage_name)
        except KeyError:
            stage = None  # fallback: stage sem wrapper (ex. futuro stage customizado)

        self._bus.publish(PipelineEvent(PipelineEvent.STAGE_STARTED, {"stage": stage_name}))
        ctx = JobContext(conn=self._conn, settings=self._settings, paths=self._paths, dry_run=dry_run)

        try:
            if stage is not None:
                result = stage.execute(ctx)
                if not result.success and result.error is not None:
                    if stage.can_retry(result.error):
                        self._bus.publish(PipelineEvent("stage_will_retry", {"stage": stage_name}))
                    else:
                        stage.rollback(ctx)
                    raise result.error
            else:
                stage_fn(conn=self._conn, dry_run=dry_run)

            self._bus.publish(PipelineEvent(PipelineEvent.STAGE_COMPLETED, {"stage": stage_name}))
        except Exception as exc:
            self._bus.publish(PipelineEvent(PipelineEvent.STAGE_ERROR, {"stage": stage_name, "error": str(exc)}))
            raise

    def run_discover(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.discover import run
        self._run_stage("discover", run, dry_run)

    def run_triage_metadata(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.triage_metadata import run
        self._run_stage("triage_metadata", run, dry_run)

    def run_triage_caption(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.triage_caption import run
        self._run_stage("triage_caption", run, dry_run)

    def run_triage_transcript(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.triage_transcript import run
        self._run_stage("triage_transcript", run, dry_run)

    def run_download(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.download import run
        self._run_stage("download", run, dry_run)

    def run_transcribe(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.transcribe import run
        self._run_stage("transcribe", run, dry_run)

    def run_find_clips(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.find_clips import run
        self._run_stage("find_clips", run, dry_run)

    def run_edit(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.edit import run
        self._run_stage("edit", run, dry_run)

    def run_thumbnail(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.thumbnail import run
        self._run_stage("thumbnail", run, dry_run)

    def run_generate_metadata(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.metadata import run
        self._run_stage("generate_metadata", run, dry_run)

    def run_upload_youtube(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.upload_youtube import run
        self._run_stage("upload_youtube", run, dry_run)

    def run_upload_tiktok(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.upload_tiktok import run
        self._run_stage("upload_tiktok", run, dry_run)

    # ------------------------------------------------------------------
    # GUI helpers — operações manuais de review
    # ------------------------------------------------------------------

    def get_clip(self, clip_id: str) -> Clip | None:
        return self._clip_repo.get(clip_id)

    def update_clip_text(
        self,
        clip_id: str,
        hook: str | None,
        payoff: str | None,
        title: str | None,
    ) -> None:
        """Persiste edições manuais de hook, payoff e título do clipe."""
        cur = self._conn.execute(
            "UPDATE clips SET hook = ?, payoff = ?, title = ?, updated_at = datetime('now') WHERE clip_id = ?",
            (hook, payoff, title, clip_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Clip não encontrado no banco: {clip_id}")
        self._conn.commit()
        self._bus.publish(PipelineEvent("clip_text_updated", {"clip_id": clip_id}))

    def approve_clip(self, clip_id: str) -> None:
        """Avança clip para o próximo status (identified → editing ou editing → edited)."""
        from canal_soberania.core.state import ClipStateMachine
        from canal_soberania.models import ClipStatus

        clip = self._clip_repo.get(clip_id)
        if clip is None:
            raise ValueError(f"Clip não encontrado: {clip_id}")

        _APPROVE_MAP: dict[ClipStatus, ClipStatus] = {
            "identified": "editing",
            "editing": "edited",
            "edited": "thumbnail_ready",
            "thumbnail_ready": "metadata_ready",
            "metadata_ready": "scheduled_youtube",
        }
        new_status = _APPROVE_MAP.get(clip.status)
        if new_status is None:
            raise ValueError(f"Clip {clip_id} em status não aprovável: {clip.status}")
        ClipStateMachine.transition(clip_id, clip.status, new_status)
        self._conn.execute(
            "UPDATE clips SET status = ?, updated_at = datetime('now') WHERE clip_id = ?",
            (new_status, clip_id),
        )
        self._conn.commit()
        self._bus.publish(PipelineEvent("clip_approved", {"clip_id": clip_id, "new_status": new_status}))

    def reject_clip(self, clip_id: str, reason: str = "Rejeitado manualmente") -> None:
        """Marca clip como erro de processamento."""
        self._conn.execute(
            "UPDATE clips SET status = 'processing_error', error_message = ?, updated_at = datetime('now') WHERE clip_id = ?",
            (reason, clip_id),
        )
        self._conn.commit()
        self._bus.publish(PipelineEvent("clip_rejected", {"clip_id": clip_id, "reason": reason}))

    def update_clip_trim(self, clip_id: str, start_s: float, end_s: float) -> None:
        """Atualiza os pontos de corte de um clipe (sem re-editar automaticamente)."""
        if end_s <= start_s:
            raise ValueError("end_s deve ser maior que start_s")
        self._conn.execute(
            "UPDATE clips SET start_s = ?, end_s = ?, updated_at = datetime('now') WHERE clip_id = ?",
            (start_s, end_s, clip_id),
        )
        self._conn.commit()
        self._bus.publish(PipelineEvent("clip_trim_updated", {"clip_id": clip_id, "start_s": start_s, "end_s": end_s}))
