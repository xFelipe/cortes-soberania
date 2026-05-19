"""Janela principal — abas Vídeos, Clipes e Pipeline."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from canal_soberania.gui.bridge import EventBridge
from canal_soberania.gui.widgets.pipeline_log import PipelineLog
from canal_soberania.gui.widgets.video_table import VideoTable
from canal_soberania.gui.workers import PipelineLoopWorker, StageWorker
from canal_soberania.models import Clip
from canal_soberania.services.pipeline_service import PipelineService

_HOOK_DISPLAY_LEN = 90
_TAB_INDEX_PIPELINE = 2

_CLIP_STATUS_COLOR: dict[str, str] = {
    "identified": "#555555",
    "editing": "#f57f17",
    "edited": "#33691e",
    "thumbnail_ready": "#1565c0",
    "metadata_ready": "#e65100",   # âmbar — aguarda aprovação manual
    "scheduled_youtube": "#004d40",
    "uploaded_youtube": "#1b5e20",
    "pending_tiktok_manual": "#e65100",
    "uploaded_tiktok": "#880e4f",
    "processing_error": "#d50000",
}

_CLIP_STATUS_LABELS: list[str] = [
    "metadata_ready",
    "edited",
    "thumbnail_ready",
    "identified",
    "editing",
    "pending_tiktok_manual",
    "scheduled_youtube",
    "uploaded_youtube",
    "uploaded_tiktok",
    "processing_error",
]


def _clip_sort_priority(status: str) -> int:
    try:
        return _CLIP_STATUS_LABELS.index(status)
    except ValueError:
        return len(_CLIP_STATUS_LABELS)


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

_STAGE_FN_MAP = {
    "run_discover": "run_discover",
    "run_triage_metadata": "run_triage_metadata",
    "run_triage_caption": "run_triage_caption",
    "run_download": "run_download",
    "run_transcribe": "run_transcribe",
    "run_triage_transcript": "run_triage_transcript",
    "run_find_clips": "run_find_clips",
    "run_edit": "run_edit",
    "run_thumbnail": "run_thumbnail",
    "run_generate_metadata": "run_generate_metadata",
    "run_upload_youtube": "run_upload_youtube",
    "run_upload_tiktok": "run_upload_tiktok",
}


class MainWindow(QMainWindow):
    def __init__(self, service: PipelineService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._worker: StageWorker | None = None

        self.setWindowTitle("Canal Soberania — Dashboard")
        self.resize(1200, 750)

        self._bridge = EventBridge(service.event_bus, self)
        self._bridge.event_received.connect(self._on_pipeline_event)

        self._setup_ui()
        self._refresh()
        self._start_pipeline_loop()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_videos_tab(), "Vídeos")
        tabs.addTab(self._build_clips_tab(), "Clipes")
        tabs.addTab(self._build_pipeline_tab(), "Pipeline")
        tabs.addTab(self._build_discover_tab(), "Discover")
        self.setCentralWidget(tabs)
        self._tabs = tabs
        self._tabs.currentChanged.connect(self._on_tab_changed)

        status_bar = QStatusBar()
        self._status_label = QLabel("Pronto")
        status_bar.addWidget(self._status_label)
        self.setStatusBar(status_bar)

    def _build_videos_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        add_btn = QPushButton("+ Adicionar vídeo")
        add_btn.clicked.connect(self._on_add_video)
        toolbar.addWidget(add_btn)
        refresh_btn = QPushButton("Atualizar lista")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        canal_urls = self._load_canal_urls()
        self._video_table = VideoTable(canal_urls=canal_urls)
        self._video_table.video_selected.connect(self._on_video_selected)
        self._video_table.video_approve_requested.connect(self._on_video_approve)
        self._video_table.video_reject_requested.connect(self._on_video_reject)
        layout.addWidget(self._video_table)
        return w

    def _on_add_video(self) -> None:
        from canal_soberania.gui.windows.add_video_dialog import AddVideoDialog

        dlg = AddVideoDialog(self._service, self)
        dlg.video_added.connect(self._on_video_added)
        dlg.exec()

    def _load_canal_urls(self) -> dict[str, str]:
        try:
            from canal_soberania.config import load_canais
            cfg = load_canais()
            return {c.id: c.channel_url for c in cfg.canais}
        except Exception:
            return {}

    def _build_clips_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Filtrar por status:"))
        self._clips_status_filter = QComboBox()
        self._clips_status_filter.addItem("Todos", None)
        for s in _CLIP_STATUS_LABELS:
            self._clips_status_filter.addItem(s, s)
        self._clips_status_filter.currentIndexChanged.connect(self._refresh_clips)
        toolbar.addWidget(self._clips_status_filter)
        toolbar.addStretch()
        refresh_btn = QPushButton("Atualizar clipes")
        refresh_btn.clicked.connect(self._refresh_clips)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._clips_container = QWidget()
        self._clips_grid = QGridLayout(self._clips_container)
        self._clips_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._clips_container)
        layout.addWidget(scroll)
        return w

    def _build_pipeline_tab(self) -> QWidget:
        self._pipeline_log = PipelineLog(run_stage_callback=self._run_stage)
        self._pipeline_log.connect_cancel(self._cancel_pipeline)
        return self._pipeline_log

    def _build_discover_tab(self) -> QWidget:
        from canal_soberania.gui.widgets.discover_panel import DiscoverPanel
        self._discover_panel = DiscoverPanel(
            service=self._service,
            refresh_videos_cb=self._refresh,
            parent=self,
        )
        return self._discover_panel

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        videos = self._service.get_videos()
        self._video_table.load(videos)
        self._refresh_clips()
        self._update_status_bar()

    def _refresh_clips(self) -> None:
        all_clips = self._service.get_clips()
        selected: str | None = self._clips_status_filter.currentData()
        clips = (
            all_clips if selected is None else [c for c in all_clips if c.status == selected]
        )
        clips = sorted(clips, key=lambda c: _clip_sort_priority(c.status))
        self._populate_clips_grid(clips)

    def _populate_clips_grid(self, clips: list[Clip]) -> None:
        # Limpar grid anterior
        while self._clips_grid.count():
            child = self._clips_grid.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()

        cols = 3
        for idx, clip in enumerate(clips):
            card = self._make_clip_card(clip)
            self._clips_grid.addWidget(card, idx // cols, idx % cols)

    def _make_clip_card(self, clip: Clip) -> QFrame:
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setFixedWidth(360)
        layout = QVBoxLayout(card)

        hook_text = clip.hook or clip.clip_id
        display = hook_text[:_HOOK_DISPLAY_LEN] + ("…" if len(hook_text) > _HOOK_DISPLAY_LEN else "")
        header_lbl = QLabel(f"<b>{display}</b>")
        header_lbl.setTextFormat(Qt.TextFormat.RichText)
        header_lbl.setWordWrap(True)
        header_lbl.setToolTip(clip.clip_id)
        layout.addWidget(header_lbl)

        status_lbl = QLabel(f"  {clip.status}  ")
        status_color = _CLIP_STATUS_COLOR.get(clip.status, "#555555")
        status_lbl.setStyleSheet(
            f"background-color: {status_color}; color: white; border-radius: 4px; padding: 1px 4px;"
        )
        status_lbl.setMaximumWidth(240)
        layout.addWidget(status_lbl)
        layout.addWidget(QLabel(f"Duração: {_fmt_duration(clip.duracao_s)}"))
        layout.addWidget(QLabel(f"Score viral: {clip.score_viral or '—'}"))

        review_btn = QPushButton("Review")
        review_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        review_btn.clicked.connect(lambda _checked=False, c=clip: self._open_review(c))
        layout.addWidget(review_btn)
        return card

    def _open_review(self, clip: Clip) -> None:
        from canal_soberania.gui.windows.clip_review import ClipReviewDialog
        dlg = ClipReviewDialog(clip, self._service, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.finished.connect(lambda _result, d=dlg: self._on_review_closed(d))
        dlg.show()

    def _on_review_closed(self, dlg: object) -> None:
        self._refresh_clips()
        if getattr(dlg, "published", False):
            self._flash_status("✓ Clipe liberado para publicação.", 4000)

    def _flash_status(self, message: str, duration_ms: int = 3000) -> None:
        self._status_label.setText(message)
        self._status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
        QTimer.singleShot(duration_ms, self._clear_flash_status)

    def _clear_flash_status(self) -> None:
        self._status_label.setStyleSheet("")
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        summary = self._service.get_status_summary()
        total = sum(summary.values())
        cost = self._service.get_monthly_cost()
        self._status_label.setText(
            f"{total} vídeo(s) no banco | Custo do mês: US$ {cost:.2f}"
        )

    # ------------------------------------------------------------------
    # Pipeline control
    # ------------------------------------------------------------------

    def _start_pipeline_loop(self) -> None:
        self._loop_worker = PipelineLoopWorker(self._service, interval_s=60, parent=self)
        self._loop_worker.iteration_done.connect(self._on_loop_iteration)
        self._loop_worker.stage_error.connect(
            lambda msg: self._status_label.setText(f"Loop: erro em stage — {msg[:80]}")
        )
        self._loop_worker.start()

    # ------------------------------------------------------------------
    # Pipeline control
    # ------------------------------------------------------------------

    def _run_stage(self, stage_method: str) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "Pipeline ocupado", "Aguarde o stage atual terminar.")
            return

        fn = getattr(self._service, stage_method, None)
        if fn is None:
            return

        self._service.reset_cancel()
        self._worker = StageWorker(fn, parent=self)
        self._worker.finished.connect(self._on_stage_done)
        self._worker.error.connect(self._on_stage_error)
        self._worker.start()
        self._status_label.setText(f"Executando: {stage_method}…")

    def _cancel_pipeline(self) -> None:
        self._service.cancel()
        self._status_label.setText("Cancelamento solicitado…")

    @Slot(int, int)
    def _on_loop_iteration(self, iteration: int, stuck: int) -> None:
        self._refresh()
        stuck_msg = f" ↺ {stuck} resetado(s)" if stuck else ""
        self._update_status_bar()
        if stuck_msg:
            self._flash_status(f"Loop #{iteration} concluído{stuck_msg}", 4000)

    @Slot()
    def _on_stage_done(self) -> None:
        self._refresh()
        self._status_label.setText("Stage concluído.")

    @Slot(str)
    def _on_stage_error(self, error: str) -> None:
        self._refresh()
        self._status_label.setText("Erro no stage — ver log.")
        QMessageBox.critical(self, "Erro no pipeline", error)

    # ------------------------------------------------------------------
    # Event bridge
    # ------------------------------------------------------------------

    @Slot(str, dict)
    def _on_pipeline_event(self, event_type: str, payload: dict) -> None:  # type: ignore[type-arg]
        if self._tabs.currentIndex() == _TAB_INDEX_PIPELINE:
            self._pipeline_log.append_event(event_type, payload)
        else:
            self._pipeline_log.append_event(event_type, payload)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        if index == 0:
            self._refresh()
        elif index == 1:
            self._refresh_clips()
        elif index == 3:
            self._discover_panel._load_canais()

    @Slot(str)
    def _on_video_added(self, video_id: str) -> None:
        self._refresh()
        self._flash_status(f"✓ Vídeo {video_id} adicionado ao pipeline.", 4000)

    @Slot(str)
    def _on_video_approve(self, video_id: str) -> None:
        try:
            self._service.approve_video(video_id)
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível aprovar", str(exc))
            return
        self._run_stage("run_pipeline_auto")
        self._status_label.setText("✓ Aprovado — pipeline em execução (download → cortes)…")

    @Slot(str)
    def _on_video_reject(self, video_id: str) -> None:
        try:
            self._service.reject_video(video_id)
            self._refresh()
            self._flash_status(f"✗ Vídeo {video_id} recusado.", 3000)
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível recusar", str(exc))

    def _on_video_selected(self, video_id: str) -> None:
        video = self._service.get_video(video_id)
        if video is None:
            return
        lines = [f"<b>{k}</b>: {v}" for k, v in video.model_dump().items() if v is not None]
        QMessageBox.information(self, f"Vídeo {video_id}", "<br>".join(lines))

    def closeEvent(self, event: QCloseEvent) -> None:
        self._loop_worker.stop()
        if self._worker and self._worker.isRunning():
            self._service.cancel()
            self._worker.wait(3000)
        self._loop_worker.wait(3000)
        self._bridge.detach()
        super().closeEvent(event)
