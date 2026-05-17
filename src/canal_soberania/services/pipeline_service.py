"""PipelineService — ponto de entrada único para CLI e futuras UIs (PySide6, FastAPI)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from canal_soberania.config import Settings
from canal_soberania.core.repositories import ClipRepository, VideoRepository
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
    ) -> None:
        self._conn = conn
        self._settings = settings
        self._paths = paths

        if video_repo is None:
            from canal_soberania.repositories.sqlite import SqliteVideoRepository
            video_repo = SqliteVideoRepository(conn)
        if clip_repo is None:
            from canal_soberania.repositories.sqlite import SqliteClipRepository
            clip_repo = SqliteClipRepository(conn)

        self._video_repo = video_repo
        self._clip_repo = clip_repo

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

    def run_discover(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.discover import run
        run(conn=self._conn, dry_run=dry_run)

    def run_triage_metadata(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.triage_metadata import run
        run(conn=self._conn, dry_run=dry_run)

    def run_triage_caption(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.triage_caption import run
        run(conn=self._conn, dry_run=dry_run)

    def run_triage_transcript(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.triage_transcript import run
        run(conn=self._conn, dry_run=dry_run)

    def run_download(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.download import run
        run(conn=self._conn, dry_run=dry_run)

    def run_transcribe(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.transcribe import run
        run(conn=self._conn, dry_run=dry_run)

    def run_find_clips(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.find_clips import run
        run(conn=self._conn, dry_run=dry_run)

    def run_edit(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.edit import run
        run(conn=self._conn, dry_run=dry_run)

    def run_thumbnail(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.thumbnail import run
        run(conn=self._conn, dry_run=dry_run)

    def run_generate_metadata(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.metadata import run
        run(conn=self._conn, dry_run=dry_run)

    def run_upload_youtube(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.upload_youtube import run
        run(conn=self._conn, dry_run=dry_run)

    def run_upload_tiktok(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.upload_tiktok import run
        run(conn=self._conn, dry_run=dry_run)
