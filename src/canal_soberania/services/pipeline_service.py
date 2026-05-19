"""PipelineService — ponto de entrada único para CLI e futuras UIs (PySide6, FastAPI)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from canal_soberania.config import Settings
from canal_soberania.core.events import EventBus, PipelineEvent
from canal_soberania.core.platforms import PlatformClient
from canal_soberania.core.repositories import ClipRepository, VideoRepository
from canal_soberania.core.stage import JobContext
from canal_soberania.core.state import ClipStateMachine, VideoStateMachine
from canal_soberania.logger import logger
from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus

# Status em que o clipe já foi enviado a pelo menos uma plataforma
_PLATFORM_STATUSES: frozenset[ClipStatus] = frozenset({
    ClipStatus.SCHEDULED_YOUTUBE,
    ClipStatus.UPLOADING_YOUTUBE,
    ClipStatus.UPLOADED_YOUTUBE,
    ClipStatus.UNSCHEDULED_YOUTUBE,
})


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
        platforms: dict[str, PlatformClient] | None = None,
    ) -> None:
        self._conn = conn
        self._settings = settings
        self._paths = paths
        self._bus = event_bus or EventBus()
        self._platforms: dict[str, PlatformClient] | None = platforms  # None = lazy init

        if video_repo is None:
            from canal_soberania.repositories.sqlite import SqliteVideoRepository
            video_repo = SqliteVideoRepository(conn)
        if clip_repo is None:
            from canal_soberania.repositories.sqlite import SqliteClipRepository
            clip_repo = SqliteClipRepository(conn)

        self._video_repo: VideoRepository = video_repo
        self._clip_repo: ClipRepository = clip_repo
        self._cancel_event = threading.Event()

        if "canais_path" in paths:
            from canal_soberania.db import ensure_canais_seeded
            ensure_canais_seeded(conn, paths["canais_path"])

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

    def run_discover(
        self,
        dry_run: bool = False,
        canal_ids: list[str] | None = None,
        janela_dias: int | None = None,
        max_videos: int | None = None,
    ) -> None:
        import functools

        from canal_soberania.stages.discover import run
        fn = functools.partial(run, canal_ids=canal_ids, janela_dias=janela_dias, max_videos=max_videos)
        self._run_stage("discover", fn, dry_run)

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

    def run_sync_youtube(self, dry_run: bool = False) -> None:
        """Sincroniza status e métricas dos clipes agendados/publicados no YouTube."""
        from canal_soberania.stages.sync_youtube import run
        self._run_stage("sync_youtube", run, dry_run)

    def reset_stuck_videos(self) -> int:
        """Reseta vídeos cujo heartbeat está ≥ 3 min atrasado (processo morreu mid-execução)."""
        _STUCK: list[tuple[str, str]] = [
            (VideoStatus.DOWNLOADING,   VideoStatus.TRIAGE_CAPTION_PASSED),
            (VideoStatus.TRANSCRIBING,  VideoStatus.DOWNLOADED),
            (VideoStatus.FINDING_CLIPS, VideoStatus.TRIAGE_TRANSCRIPT_PASSED),
        ]
        return self._video_repo.reset_stuck(_STUCK)

    def reset_stuck_clips(self) -> int:
        """Reseta clipes cujo heartbeat está ≥ 3 min atrasado (processo morreu mid-execução)."""
        _STUCK_CLIPS: list[tuple[str, str]] = [
            (ClipStatus.EDITING, ClipStatus.IDENTIFIED),
        ]
        return self._clip_repo.reset_stuck(_STUCK_CLIPS)

    def run_pipeline_auto(self, dry_run: bool = False) -> None:
        """Roda todos os stages automáticos em sequência: triagem → download → transcrição
        → identificação de cortes → edição → thumbnail → metadados.

        Cada stage processa todos os vídeos/clipes pendentes naquela etapa.
        Stages sem trabalho concluem rapidamente.
        Erros em um stage são logados mas não interrompem os stages seguintes.
        """
        from canal_soberania.logger import logger

        stages = [
            ("triage_metadata",   self.run_triage_metadata),
            ("triage_caption",    self.run_triage_caption),
            ("download",          self.run_download),
            ("transcribe",        self.run_transcribe),
            ("triage_transcript", self.run_triage_transcript),
            ("find_clips",        self.run_find_clips),
            ("edit",              self.run_edit),
            ("thumbnail",         self.run_thumbnail),
            ("generate_metadata", self.run_generate_metadata),
        ]
        for stage_name, fn in stages:
            if self._cancel_event.is_set():
                break
            try:
                fn(dry_run=dry_run)
            except Exception as exc:
                logger.warning(
                    "run_pipeline_auto: stage '{}' falhou (continuando): {}", stage_name, exc
                )

    # ------------------------------------------------------------------
    # GUI helpers — operações manuais de review
    # ------------------------------------------------------------------

    def get_clip(self, clip_id: str) -> Clip | None:
        return self._clip_repo.get(clip_id)

    def approve_video(self, video_id: str) -> None:
        """Avança vídeo manualmente para a próxima etapa do pipeline."""
        video = self._video_repo.get(video_id)
        if video is None:
            raise ValueError(f"Vídeo não encontrado: {video_id}")
        VS = VideoStatus
        _APPROVE_MAP: dict[VideoStatus, VideoStatus] = {
            VS.DISCOVERED: VS.TRIAGE_METADATA_PASSED,
            VS.TRIAGE_METADATA_REJECTED: VS.TRIAGE_METADATA_PASSED,
            VS.ON_HOLD_METADATA_PASSED: VS.TRIAGE_CAPTION_PASSED,
            VS.TRIAGE_METADATA_PASSED: VS.TRIAGE_CAPTION_PASSED,
            VS.TRIAGE_CAPTION_REJECTED: VS.TRIAGE_CAPTION_PASSED,
            VS.TRIAGE_CAPTION_SKIPPED: VS.DOWNLOADING,
            VS.TRIAGE_CAPTION_PASSED: VS.DOWNLOADING,
            VS.TRANSCRIBE_ERROR: VS.TRANSCRIBED,
            VS.TRIAGE_TRANSCRIPT_REJECTED: VS.APPROVED_FOR_CLIPS,
            VS.TRANSCRIBED: VS.TRIAGE_TRANSCRIPT_PASSED,
            VS.TRIAGE_TRANSCRIPT_PASSED: VS.APPROVED_FOR_CLIPS,
        }
        new_status = _APPROVE_MAP.get(video.status)
        if new_status is None:
            raise ValueError(f"Vídeo '{video_id}' em status não aprovável manualmente: {video.status}")
        self._video_repo.update_status(video_id, new_status)
        self._bus.publish(PipelineEvent("video_approved", {"video_id": video_id, "new_status": new_status}))

    def reject_video(self, video_id: str) -> None:
        """Rejeita manualmente um vídeo, marcando como triage_metadata_rejected."""
        self._video_repo.reject(video_id)
        self._bus.publish(PipelineEvent("video_rejected", {"video_id": video_id}))

    def _get_youtube(self) -> PlatformClient:
        """Retorna o cliente YouTube (cria lazy se não injetado)."""
        if self._platforms is not None and "youtube" in self._platforms:
            return self._platforms["youtube"]
        from canal_soberania.core.platforms import get_platform
        yt = get_platform("youtube", self._settings)
        if self._platforms is None:
            self._platforms = {}
        self._platforms["youtube"] = yt
        return yt

    def update_clip_text(
        self,
        clip_id: str,
        hook: str | None,
        payoff: str | None,
        title: str | None,
        youtube_publish_at: str | None,
        render_vertical: bool = True,
        render_horizontal: bool = True,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Persiste edições manuais e propaga às plataformas se o clipe já foi enviado."""
        old = self._clip_repo.get(clip_id)
        if old is None:
            raise ValueError(f"Clip não encontrado: {clip_id}")

        # Persiste campos editáveis (description/tags via update_metadata_fields)
        self._clip_repo.update_metadata_fields(
            clip_id,
            hook=hook,
            payoff=payoff,
            title=title,
            description=description,
            tags=tags,
            youtube_publish_at=youtube_publish_at,
            render_vertical=render_vertical,
            render_horizontal=render_horizontal,
        )
        # Propaga a plataformas se o clipe já está em alguma delas
        if old.status in _PLATFORM_STATUSES:
            self._propagate_metadata_changes(
                old, title=title, description=description,
                tags=tags, publish_at=youtube_publish_at,
            )
            self._propagate_format_changes(old, render_vertical, render_horizontal)

        self._bus.publish(PipelineEvent("clip_text_updated", {"clip_id": clip_id}))

    def _propagate_metadata_changes(
        self,
        old: Clip,
        *,
        title: str | None,
        description: str | None,
        tags: list[str] | None,
        publish_at: str | None,
    ) -> None:
        """Chama update_metadata no YouTube se algum campo de texto mudou."""
        meta_changed = (
            (title is not None and title != old.title)
            or (description is not None and description != old.description)
            or (tags is not None and tags != old.tags)
        )
        schedule_changed = publish_at is not None and publish_at != old.youtube_publish_at

        if not meta_changed and not schedule_changed:
            return

        yt = self._get_youtube()
        # Vertical (Short): título recebe prefixo #Shorts
        if old.youtube_id:
            short_title = f"#Shorts {title[:93]}" if title is not None else None
            try:
                yt.update_metadata(
                    old.youtube_id,
                    title=short_title,
                    description=description,
                    tags=tags,
                    publish_at=publish_at if schedule_changed else None,
                )
            except Exception as exc:
                logger.error(
                    "propagate_metadata: falha ao atualizar vertical {}: {}", old.youtube_id, exc
                )
                raise

        # Horizontal: título sem prefixo
        if old.youtube_id_horizontal:
            horiz_title = title[:100] if title is not None else None
            try:
                yt.update_metadata(
                    old.youtube_id_horizontal,
                    title=horiz_title,
                    description=description,
                    tags=tags,
                    publish_at=publish_at if schedule_changed else None,
                )
            except Exception as exc:
                logger.error(
                    "propagate_metadata: falha ao atualizar horizontal {}: {}",
                    old.youtube_id_horizontal, exc,
                )
                raise

    def _propagate_format_changes(
        self, old: Clip, new_render_v: bool, new_render_h: bool
    ) -> None:
        """Deleta ou marca para re-upload quando os formatos de saída mudam."""
        yt = self._get_youtube()
        v_deleted = h_deleted = False

        # Vertical removido
        if old.render_vertical and not new_render_v and old.youtube_id:
            try:
                yt.delete(old.youtube_id)
                self._clip_repo.clear_platform_id(old.clip_id, kind="vertical")
                logger.info("propagate_formats: deletado vertical {}", old.youtube_id)
                v_deleted = True
            except Exception as exc:
                logger.error(
                    "propagate_formats: falha ao deletar vertical {}: {}", old.youtube_id, exc
                )
                raise

        # Horizontal removido
        if old.render_horizontal and not new_render_h and old.youtube_id_horizontal:
            try:
                yt.delete(old.youtube_id_horizontal)
                self._clip_repo.clear_platform_id(old.clip_id, kind="horizontal")
                logger.info("propagate_formats: deletado horizontal {}", old.youtube_id_horizontal)
                h_deleted = True
            except Exception as exc:
                logger.error(
                    "propagate_formats: falha ao deletar horizontal {}: {}",
                    old.youtube_id_horizontal, exc,
                )
                raise

        # Se ambos foram deletados → transiciona para deleted_youtube
        both_gone = (
            (v_deleted or not old.youtube_id)
            and (h_deleted or not old.youtube_id_horizontal)
        )
        if both_gone and old.status in _PLATFORM_STATUSES:
            try:
                ClipStateMachine.transition(old.clip_id, old.status, ClipStatus.DELETED_YOUTUBE)
                self._clip_repo.update_status(old.clip_id, ClipStatus.DELETED_YOUTUBE)
            except Exception as exc:
                logger.error(
                    "propagate_formats: falha ao transicionar {}: {}", old.clip_id, exc
                )
                raise
        # Novos formatos marcados (sem ID existente) → upload ocorre na próxima execução
        # do stage upload_youtube; apenas salvar o flag (já feito em update_metadata_fields)

    def unschedule_clip(self, clip_id: str) -> None:
        """Cancela agendamento no YouTube; status → unscheduled_youtube."""
        clip = self._clip_repo.get(clip_id)
        if clip is None:
            raise ValueError(f"Clip não encontrado: {clip_id}")

        yt = self._get_youtube()
        if clip.youtube_id:
            yt.unschedule(clip.youtube_id)
        if clip.youtube_id_horizontal:
            yt.unschedule(clip.youtube_id_horizontal)

        ClipStateMachine.transition(clip_id, clip.status, ClipStatus.UNSCHEDULED_YOUTUBE)
        self._clip_repo.update_status(clip_id, ClipStatus.UNSCHEDULED_YOUTUBE)
        self._clip_repo.update_metadata_fields(clip_id, youtube_publish_at="")
        self._bus.publish(PipelineEvent("clip_unscheduled", {"clip_id": clip_id}))

    def discard_clip(self, clip_id: str) -> None:
        """Deleta vídeo(s) do YouTube e marca o clipe como deleted_youtube."""
        clip = self._clip_repo.get(clip_id)
        if clip is None:
            raise ValueError(f"Clip não encontrado: {clip_id}")

        yt = self._get_youtube()
        if clip.youtube_id:
            yt.delete(clip.youtube_id)
            self._clip_repo.clear_platform_id(clip_id, kind="vertical")
        if clip.youtube_id_horizontal:
            yt.delete(clip.youtube_id_horizontal)
            self._clip_repo.clear_platform_id(clip_id, kind="horizontal")

        ClipStateMachine.transition(clip_id, clip.status, ClipStatus.DELETED_YOUTUBE)
        self._clip_repo.update_status(clip_id, ClipStatus.DELETED_YOUTUBE)
        self._bus.publish(PipelineEvent("clip_discarded", {"clip_id": clip_id}))

    def approve_clip(self, clip_id: str) -> None:
        """Avança clip para o próximo status."""
        from canal_soberania.core.state import ClipStateMachine

        clip = self._clip_repo.get(clip_id)
        if clip is None:
            raise ValueError(f"Clip não encontrado: {clip_id}")

        CS = ClipStatus
        _APPROVE_MAP: dict[ClipStatus, ClipStatus] = {
            CS.IDENTIFIED: CS.EDITING,
            CS.EDITING: CS.EDITED,
            CS.EDITED: CS.THUMBNAIL_READY,
            CS.THUMBNAIL_READY: CS.METADATA_READY,
            CS.METADATA_READY: CS.SCHEDULED_YOUTUBE,
        }
        new_status = _APPROVE_MAP.get(clip.status)
        if new_status is None:
            raise ValueError(f"Clip {clip_id} em status não aprovável: {clip.status}")
        ClipStateMachine.transition(clip_id, clip.status, new_status)
        self._clip_repo.update_status(clip_id, new_status)
        self._bus.publish(PipelineEvent("clip_approved", {"clip_id": clip_id, "new_status": new_status}))

    def reject_clip(self, clip_id: str, reason: str = "Rejeitado manualmente") -> None:
        """Marca clip como erro de processamento."""
        self._clip_repo.reject(clip_id, reason)
        self._bus.publish(PipelineEvent("clip_rejected", {"clip_id": clip_id, "reason": reason}))

    def restore_clip(self, clip_id: str) -> None:
        """Desfaz rejeição manual: processing_error → identified."""

        self._clip_repo.restore(clip_id)
        self._bus.publish(PipelineEvent("clip_restored", {"clip_id": clip_id}))

    def mark_video_burned_subtitles(self, video_id: str, has_subs: bool) -> int:
        """Marca o vídeo como tendo (ou não) legenda queimada e re-enfileira os clipes para re-edit.

        Retorna o número de clipes re-enfileirados.
        """
        with self._conn:
            self._conn.execute(
                "UPDATE videos SET legendas_queimadas = ?, updated_at = datetime('now') WHERE video_id = ?",
                (1 if has_subs else 0, video_id),
            )
            if has_subs:
                cur = self._conn.execute(
                    "UPDATE clips SET status = ?, "
                    "clip_path_vertical = NULL, clip_path_horizontal = NULL, "
                    "updated_at = datetime('now') "
                    "WHERE video_id = ? AND status NOT IN (?)",
                    (ClipStatus.IDENTIFIED, video_id, ClipStatus.PROCESSING_ERROR),
                )
                count = cur.rowcount
            else:
                count = 0
        self._bus.publish(PipelineEvent("video_burned_subtitles_updated", {
            "video_id": video_id, "has_subs": has_subs, "clips_requeued": count,
        }))
        return count

    def add_video_by_id(self, video_id: str) -> Video:
        """Busca metadados do vídeo na YouTube API e insere no pipeline com status 'discovered'.

        Usa canal_id='manual' para vídeos adicionados fora do discover automático.
        Levanta ValueError se o vídeo não for encontrado ou a API key não estiver configurada.
        """
        from googleapiclient.discovery import build

        from canal_soberania.db import insert_video
        from canal_soberania.stages.discover import _parse_duration, fetch_video_details

        if not self._settings.youtube_api_key:
            raise ValueError("youtube_api_key não está configurada em .env")

        youtube = build("youtube", "v3", developerKey=self._settings.youtube_api_key)
        details = fetch_video_details(youtube, [video_id])
        if not details:
            raise ValueError(f"Vídeo '{video_id}' não encontrado ou inacessível no YouTube.")

        item = details[0]
        snippet: dict[str, Any] = item.get("snippet", {})
        stats: dict[str, Any] = item.get("statistics", {})
        content: dict[str, Any] = item.get("contentDetails", {})

        video = Video(
            video_id=video_id,
            canal_id="manual",
            title=snippet.get("title", ""),
            description=snippet.get("description") or None,
            tags=snippet.get("tags", []),
            published_at=snippet.get("publishedAt", ""),
            duration_s=_parse_duration(content.get("duration", "")) if content.get("duration") else None,
            view_count=int(stats["viewCount"]) if "viewCount" in stats else None,
            like_count=int(stats["likeCount"]) if "likeCount" in stats else None,
            comment_count=int(stats["commentCount"]) if "commentCount" in stats else None,
        )

        already = self._conn.execute(
            "SELECT 1 FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        if already:
            raise ValueError(f"Vídeo '{video_id}' já está no banco de dados.")

        with self._conn:
            insert_video(self._conn, video)

        self._bus.publish(PipelineEvent("video_added_manually", {"video_id": video_id, "title": video.title}))
        return video

    def update_clip_trim(self, clip_id: str, start_s: float, end_s: float) -> None:
        """Atualiza os pontos de corte e re-enfileira o clipe para re-edição automática."""
        if end_s <= start_s:
            raise ValueError("end_s deve ser maior que start_s")

        # Apaga arquivos renderizados em disco para forçar re-encode
        clip = self._clip_repo.get(clip_id)
        if clip and clip.status != ClipStatus.PROCESSING_ERROR:
            from pathlib import Path
            for p in (clip.clip_path_vertical, clip.clip_path_horizontal):
                if p:
                    Path(p).unlink(missing_ok=True)

        with self._conn:
            self._conn.execute(
                f"""UPDATE clips
                   SET start_s = ?,
                       end_s = ?,
                       status = CASE WHEN status = '{ClipStatus.PROCESSING_ERROR}' THEN status ELSE '{ClipStatus.IDENTIFIED}' END,
                       clip_path_vertical   = CASE WHEN status = '{ClipStatus.PROCESSING_ERROR}' THEN clip_path_vertical   ELSE NULL END,
                       clip_path_horizontal = CASE WHEN status = '{ClipStatus.PROCESSING_ERROR}' THEN clip_path_horizontal ELSE NULL END,
                       updated_at = datetime('now')
                   WHERE clip_id = ?""",  # noqa: S608
                (start_s, end_s, clip_id),
            )
        self._bus.publish(PipelineEvent("clip_trim_updated", {"clip_id": clip_id, "start_s": start_s, "end_s": end_s}))

    # ------------------------------------------------------------------
    # Gerenciamento de canais
    # ------------------------------------------------------------------

    def get_canais(self, apenas_ativos: bool = False) -> list[Any]:
        from canal_soberania.repositories.sqlite import SqliteCanaisRepository
        repo = SqliteCanaisRepository(self._conn)
        return repo.get_active() if apenas_ativos else repo.get_all()

    def upsert_canal(self, canal: Any) -> None:
        from canal_soberania.repositories.sqlite import SqliteCanaisRepository
        SqliteCanaisRepository(self._conn).upsert(canal)
        self._bus.publish(PipelineEvent("canal_upserted", {"canal_id": canal.id}))

    def toggle_canal_ativo(self, canal_id: str, ativo: bool) -> None:
        from canal_soberania.repositories.sqlite import SqliteCanaisRepository
        SqliteCanaisRepository(self._conn).set_active(canal_id, ativo)
        self._bus.publish(PipelineEvent("canal_toggled", {"canal_id": canal_id, "ativo": ativo}))

    def delete_canal(self, canal_id: str) -> None:
        from canal_soberania.repositories.sqlite import SqliteCanaisRepository
        SqliteCanaisRepository(self._conn).delete(canal_id)
        self._bus.publish(PipelineEvent("canal_deleted", {"canal_id": canal_id}))

    def discover_adhoc(
        self,
        channel_url_or_handle: str,
        persist: bool = False,
        janela_dias: int | None = None,
        max_videos: int | None = None,
        dry_run: bool = False,
    ) -> int:
        """Roda discover em um canal ad-hoc (não necessariamente cadastrado).

        Se persist=True, salva o canal na tabela canais.
        Retorna o número de vídeos inseridos.
        """
        from googleapiclient.discovery import build

        from canal_soberania.config import get_paths, load_canais
        from canal_soberania.stages.discover import discover_canal_adhoc

        if not self._settings.youtube_api_key:
            raise ValueError("YOUTUBE_API_KEY não está configurada em .env")

        youtube = build("youtube", "v3", developerKey=self._settings.youtube_api_key)
        paths = get_paths(self._settings)
        canais_cfg = load_canais(paths["canais_path"])
        parametros = canais_cfg.parametros
        if janela_dias is not None:
            parametros = parametros.model_copy(update={"janela_dias_discover": janela_dias})
        if max_videos is not None:
            parametros = parametros.model_copy(update={"max_videos_por_canal_por_run": max_videos})

        ins, canal = discover_canal_adhoc(
            youtube, channel_url_or_handle, parametros, self._conn,
            dry_run=dry_run, persist=persist,
        )
        if canal is not None:
            self._bus.publish(PipelineEvent("canal_upserted", {"canal_id": canal.id}))
        self._bus.publish(PipelineEvent(
            "discover_adhoc_done",
            {"handle": channel_url_or_handle, "inserted": ins, "persisted": persist},
        ))
        return ins
