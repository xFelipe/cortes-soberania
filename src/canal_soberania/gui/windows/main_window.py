"""Janela principal — abas Vídeos, Clipes e Pipeline."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
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
    QGridLayout,
    QFrame,
)

from canal_soberania.gui.bridge import EventBridge
from canal_soberania.gui.widgets.pipeline_log import PipelineLog
from canal_soberania.gui.widgets.video_table import VideoTable
from canal_soberania.gui.workers import StageWorker
from canal_soberania.models import Clip
from canal_soberania.services.pipeline_service import PipelineService

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

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_videos_tab(), "Vídeos")
        tabs.addTab(self._build_clips_tab(), "Clipes")
        tabs.addTab(self._build_pipeline_tab(), "Pipeline")
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

        refresh_btn = QPushButton("Atualizar lista")
        refresh_btn.clicked.connect(self._refresh)
        layout.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignRight)

        canal_urls = self._load_canal_urls()
        self._video_table = VideoTable(canal_urls=canal_urls)
        self._video_table.video_selected.connect(self._on_video_selected)
        layout.addWidget(self._video_table)
        return w

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

        refresh_btn = QPushButton("Atualizar clipes")
        refresh_btn.clicked.connect(self._refresh_clips)
        layout.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignRight)

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

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        videos = self._service.get_videos()
        self._video_table.load(videos)
        self._refresh_clips()
        self._update_status_bar()

    def _refresh_clips(self) -> None:
        clips = self._service.get_clips()
        self._populate_clips_grid(clips)

    def _populate_clips_grid(self, clips: list[Clip]) -> None:
        # Limpar grid anterior
        while self._clips_grid.count():
            child = self._clips_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        cols = 3
        for idx, clip in enumerate(clips):
            card = self._make_clip_card(clip)
            self._clips_grid.addWidget(card, idx // cols, idx % cols)

    def _make_clip_card(self, clip: Clip) -> QFrame:
        from canal_soberania.gui.windows.clip_review import ClipReviewDialog

        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setFixedWidth(360)
        layout = QVBoxLayout(card)

        clip_id_lbl = QLabel(f"<b>{clip.clip_id}</b>")
        clip_id_lbl.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(clip_id_lbl)

        layout.addWidget(QLabel(f"Status: {clip.status}"))
        layout.addWidget(QLabel(f"Duração: {clip.duracao_s:.1f}s"))
        layout.addWidget(QLabel(f"Score viral: {clip.score_viral or '—'}"))
        if clip.hook:
            hook_lbl = QLabel(clip.hook[:80] + ("…" if len(clip.hook) > 80 else ""))
            hook_lbl.setWordWrap(True)
            layout.addWidget(hook_lbl)

        review_btn = QPushButton("Review")
        review_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        review_btn.clicked.connect(lambda _checked=False, c=clip: ClipReviewDialog(c, self._service, self).exec())
        layout.addWidget(review_btn)
        return card

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
        if self._tabs.currentIndex() == 2:
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

    def _on_video_selected(self, video_id: str) -> None:
        video = self._service.get_video(video_id)
        if video is None:
            return
        lines = [f"<b>{k}</b>: {v}" for k, v in video.model_dump().items() if v is not None]
        QMessageBox.information(self, f"Vídeo {video_id}", "<br>".join(lines))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._worker and self._worker.isRunning():
            self._service.cancel()
            self._worker.wait(3000)
        self._bridge.detach()
        super().closeEvent(event)
