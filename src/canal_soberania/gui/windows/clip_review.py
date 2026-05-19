"""Diálogo de review de clipes: player de preview + aprovação/rejeição/trim."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QDateTime, QRectF, QSizeF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QCursor,
    QDesktopServices,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from canal_soberania.models import Clip, ClipStatus
from canal_soberania.services.pipeline_service import PipelineService

_DESC_PREVIEW_LEN = 300


class _SeekSlider(QSlider):
    """QSlider com jump-to-click e marcas visuais de in/out."""

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._in_ms: int = 0
        self._out_ms: int = 0
        self._duration_ms: int = 0

    def set_bounds(self, in_ms: int, out_ms: int, duration_ms: int) -> None:
        self._in_ms = in_ms
        self._out_ms = out_ms
        self._duration_ms = duration_ms
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(event.position().x()), self.width()
            )
            self.setValue(val)
            self.sliderMoved.emit(val)
        super().mousePressEvent(event)

    def paintEvent(self, event: object) -> None:  # type: ignore[override]
        super().paintEvent(event)  # type: ignore[arg-type]
        if self._duration_ms <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        w = self.width()
        for ms, color in [(self._in_ms, QColor(80, 200, 80, 220)), (self._out_ms, QColor(220, 80, 80, 220))]:
            x = int(ms / self._duration_ms * w)
            pen = QPen(color, 2)
            painter.setPen(pen)
            painter.drawLine(x, 0, x, h)
        painter.end()


class _VerticalMask(QGraphicsRectItem):
    """Overlay que escurece as laterais fora da janela 9:16."""

    def __init__(self) -> None:
        super().__init__()
        self._crop_x: float = 0.0
        self._crop_w: float = 0.0
        self._vid_w: float = 0.0
        self._vid_h: float = 0.0
        self.setZValue(10)

    def set_viewport(self, vid_w: float, vid_h: float, crop_x: float) -> None:
        self._vid_w = vid_w
        self._vid_h = vid_h
        self._crop_w = vid_h * 9.0 / 16.0
        self._crop_x = crop_x
        self.setRect(QRectF(0, 0, vid_w, vid_h))

    def paint(
        self, painter: QPainter, option: object, widget: object = None  # type: ignore[override]
    ) -> None:
        if self._vid_w <= 0:
            return
        overlay = QColor(0, 0, 0, 130)
        painter.setBrush(QBrush(overlay))
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        # faixa esquerda
        painter.drawRect(QRectF(0, 0, self._crop_x, self._vid_h))
        # faixa direita
        right_x = self._crop_x + self._crop_w
        painter.drawRect(QRectF(right_x, 0, self._vid_w - right_x, self._vid_h))
        # borda da área ativa
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 160), 1.5))
        painter.drawRect(QRectF(self._crop_x, 0, self._crop_w, self._vid_h))


class ClipReviewDialog(QDialog):
    """Abre um clipe para review: player, edição de textos, trim e aprovação.

    Atalhos (fora de campos de texto):
        Space = play/pause | A = aprovar | R = rejeitar
        [ = marcar início na posição atual | ] = marcar fim na posição atual
    """

    _face_detected = Signal(object)  # int | None — crop_x do rosto

    def __init__(
        self, clip: Clip, service: PipelineService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._clip = clip
        self._service = service
        self.published = False
        self._loop_start_ms: int = int(clip.start_s * 1000)
        self._loop_end_ms: int = int(clip.end_s * 1000)
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._refresh_loop_bounds)
        self._vid_natural_w: int = 0
        self._vid_natural_h: int = 0
        self.setWindowTitle(f"Review — {clip.clip_id}")
        self.resize(960, 700)
        self._setup_ui()
        self._load_source_video()

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)

        # ── Esquerda: player ──────────────────────────────────────────
        left = QVBoxLayout()

        # QGraphicsView com QGraphicsVideoItem para suportar overlay
        self._scene = QGraphicsScene(self)
        self._video_item = QGraphicsVideoItem()
        self._scene.addItem(self._video_item)
        self._mask = _VerticalMask()
        self._scene.addItem(self._mask)

        self._gfx_view = QGraphicsView(self._scene)
        self._gfx_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gfx_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gfx_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._gfx_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._gfx_view.setMinimumSize(480, 270)
        self._gfx_view.setStyleSheet("background: black; border: none;")
        left.addWidget(self._gfx_view)

        self._no_video_label = QLabel(
            "Arquivo de vídeo-fonte não encontrado.\n"
            "Verifique se o download foi realizado."
        )
        self._no_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_video_label.setVisible(False)
        left.addWidget(self._no_video_label)

        self._seek_bar = _SeekSlider(Qt.Orientation.Horizontal)
        self._seek_bar.setRange(0, 0)
        self._seek_bar.setEnabled(False)
        self._seek_bar.sliderMoved.connect(self._on_seek)
        left.addWidget(self._seek_bar)

        ctrl = QHBoxLayout()
        self._play_btn = QPushButton("▶ Play")
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._play_btn)
        self._pos_label = QLabel("0:00 / 0:00")
        ctrl.addWidget(self._pos_label)
        ctrl.addStretch()
        left.addLayout(ctrl)

        root.addLayout(left, 3)

        # ── Direita: info + textos editáveis + trim + ações ──────────
        right = QVBoxLayout()

        info_group = QGroupBox("Informações do clipe")
        info_layout = QFormLayout(info_group)
        info_layout.addRow("ID:", QLabel(self._clip.clip_id))
        info_layout.addRow("Vídeo:", self._make_video_link())
        info_layout.addRow("Status:", QLabel(self._clip.status))
        info_layout.addRow("Score viral:", QLabel(str(self._clip.score_viral or "—")))
        info_layout.addRow("Score relevância:", QLabel(str(self._clip.score_relevancia or "—")))
        info_layout.addRow("Tema:", QLabel(self._clip.tema_soberania or "—"))

        video = self._service.get_video(self._clip.video_id)
        self._burned_subs_chk = QCheckBox("Vídeo já vem com legenda queimada")
        self._burned_subs_chk.setChecked(bool(video.legendas_queimadas) if video else False)
        self._burned_subs_chk.setToolTip(
            "Marque se o vídeo original já possui legendas na imagem.\n"
            "Os clipes deste vídeo serão re-editados sem legenda sobreposta."
        )
        self._burned_subs_chk.toggled.connect(self._on_burned_subs_toggled)
        info_layout.addRow(self._burned_subs_chk)

        right.addWidget(info_group)

        edit_group = QGroupBox("Textos (editável)")
        edit_layout = QFormLayout(edit_group)

        self._title_edit = QLineEdit(self._clip.title or "")
        self._title_edit.setPlaceholderText("Título para YouTube…")
        edit_layout.addRow("Título:", self._title_edit)

        self._hook_te = QTextEdit(self._clip.hook or "")
        self._hook_te.setMaximumHeight(72)
        self._hook_te.setPlaceholderText("Hook do clipe…")
        edit_layout.addRow("Hook:", self._hook_te)

        self._payoff_te = QTextEdit(self._clip.payoff or "")
        self._payoff_te.setMaximumHeight(72)
        self._payoff_te.setPlaceholderText("Payoff do clipe…")
        edit_layout.addRow("Payoff:", self._payoff_te)

        self._description_te = QTextEdit(self._clip.description or "")
        self._description_te.setMaximumHeight(80)
        self._description_te.setPlaceholderText("Descrição para YouTube / TikTok…")
        edit_layout.addRow("Descrição:", self._description_te)

        tags_str = ", ".join(self._clip.tags) if self._clip.tags else ""
        self._tags_edit = QLineEdit(tags_str)
        self._tags_edit.setPlaceholderText("tag1, tag2, tag3… (máx 15)")
        edit_layout.addRow("Tags:", self._tags_edit)

        sched_row = QWidget()
        sched_row_layout = QHBoxLayout(sched_row)
        sched_row_layout.setContentsMargins(0, 0, 0, 0)
        self._schedule_chk = QCheckBox("Agendar publicação")
        self._schedule_dt = QDateTimeEdit()
        self._schedule_dt.setDisplayFormat("dd/MM/yyyy HH:mm")
        self._schedule_dt.setCalendarPopup(True)
        has_schedule = bool(self._clip.youtube_publish_at)
        self._schedule_chk.setChecked(has_schedule)
        if has_schedule:
            dt = QDateTime.fromString((self._clip.youtube_publish_at or "")[:16], "yyyy-MM-ddTHH:mm")
            self._schedule_dt.setDateTime(dt if dt.isValid() else QDateTime.currentDateTime().addDays(1))
        else:
            self._schedule_dt.setDateTime(QDateTime.currentDateTime().addDays(1))
        self._schedule_dt.setEnabled(has_schedule)
        self._schedule_chk.toggled.connect(self._schedule_dt.setEnabled)
        sched_row_layout.addWidget(self._schedule_chk)
        sched_row_layout.addWidget(self._schedule_dt, 1)
        edit_layout.addRow(sched_row)

        self._save_btn = QPushButton("Salvar alterações")
        self._save_btn.clicked.connect(lambda: self._save_changes(silent=False))
        edit_layout.addRow(self._save_btn)

        right.addWidget(edit_group)

        is_scheduled = self._clip.status in {ClipStatus.SCHEDULED_YOUTUBE, ClipStatus.UPLOADED_YOUTUBE,
                                             ClipStatus.UPLOADING_YOUTUBE}
        formats_group = QGroupBox("Formatos de saída")
        formats_layout = QVBoxLayout(formats_group)
        self._render_vertical_chk = QCheckBox("Vertical (9:16 — Shorts / TikTok)")
        self._render_vertical_chk.setChecked(self._clip.render_vertical)
        self._render_horizontal_chk = QCheckBox("Horizontal (16:9 — YouTube)")
        self._render_horizontal_chk.setChecked(self._clip.render_horizontal)
        if is_scheduled:
            v_has_id = bool(self._clip.youtube_id)
            h_has_id = bool(self._clip.youtube_id_horizontal)
            self._render_vertical_chk.setToolTip(
                "Desmarcar vai deletar o Short do YouTube" if v_has_id
                else "Marcar vai fazer upload do Short na próxima execução do pipeline"
            )
            self._render_horizontal_chk.setToolTip(
                "Desmarcar vai deletar o vídeo horizontal do YouTube" if h_has_id
                else "Marcar vai fazer upload horizontal na próxima execução do pipeline"
            )
        formats_layout.addWidget(self._render_vertical_chk)
        formats_layout.addWidget(self._render_horizontal_chk)
        right.addWidget(formats_group)

        # Trim — live preview; salvar persiste no DB e agenda re-render
        trim_group = QGroupBox("Editar trim")
        trim_layout = QFormLayout(trim_group)
        self._start_spin = QDoubleSpinBox()
        self._start_spin.setRange(0, 86400)
        self._start_spin.setDecimals(1)
        self._start_spin.setSuffix(" s")
        self._start_spin.setValue(self._clip.start_s)
        self._start_spin.valueChanged.connect(self._on_trim_changed)
        trim_layout.addRow("Início:", self._start_spin)
        self._end_spin = QDoubleSpinBox()
        self._end_spin.setRange(0, 86400)
        self._end_spin.setDecimals(1)
        self._end_spin.setSuffix(" s")
        self._end_spin.setValue(self._clip.end_s)
        self._end_spin.valueChanged.connect(self._on_trim_changed)
        trim_layout.addRow("Fim:", self._end_spin)
        self._apply_trim_btn = QPushButton("Salvar trim")
        self._apply_trim_btn.setToolTip(
            "Persiste início/fim no banco e agenda re-render.\n"
            "O preview acima já reflete o trim ao vivo — salve quando estiver satisfeito."
        )
        self._apply_trim_btn.clicked.connect(self._apply_trim)
        trim_layout.addRow(self._apply_trim_btn)
        if is_scheduled:
            self._start_spin.setEnabled(False)
            self._end_spin.setEnabled(False)
            self._apply_trim_btn.setEnabled(False)
            trim_group.setToolTip("Cancele o agendamento primeiro para alterar o corte.")
        right.addWidget(trim_group)

        right.addStretch()

        btn_box = QDialogButtonBox()
        approve_label = (
            "Liberar para publicação" if self._clip.status == ClipStatus.METADATA_READY else "Aprovar etapa"
        )
        self._approve_btn = btn_box.addButton(approve_label, QDialogButtonBox.ButtonRole.AcceptRole)
        self._approve_btn.setStyleSheet("background-color: #2e7d32; color: white;")
        self._approve_btn.clicked.connect(self._approve)

        self._unschedule_btn: QPushButton | None = None
        self._discard_btn: QPushButton | None = None

        if self._clip.status in {ClipStatus.SCHEDULED_YOUTUBE, ClipStatus.UPLOADED_YOUTUBE, ClipStatus.UPLOADING_YOUTUBE}:
            self._unschedule_btn = btn_box.addButton(
                "Cancelar agendamento", QDialogButtonBox.ButtonRole.ActionRole
            )
            self._unschedule_btn.setStyleSheet("background-color: #e65100; color: white;")
            self._unschedule_btn.setToolTip("Torna o vídeo privado sem data de publicação (reversível)")
            self._unschedule_btn.clicked.connect(self._do_unschedule)

            self._discard_btn = btn_box.addButton(
                "Descartar", QDialogButtonBox.ButtonRole.RejectRole
            )
            self._discard_btn.setStyleSheet("background-color: #b71c1c; color: white;")
            self._discard_btn.setToolTip("Deleta o vídeo do YouTube permanentemente")
            self._discard_btn.clicked.connect(self._do_discard)

            self._reject_btn = self._discard_btn
        else:
            self._reject_btn = btn_box.addButton("Rejeitar", QDialogButtonBox.ButtonRole.RejectRole)
            self._reject_btn.setStyleSheet("background-color: #b71c1c; color: white;")
            self._reject_btn.clicked.connect(self._toggle_reject)

        close_btn = btn_box.addButton("Fechar", QDialogButtonBox.ButtonRole.DestructiveRole)
        close_btn.clicked.connect(self.reject)
        right.addWidget(btn_box)

        if self._clip.status == ClipStatus.PROCESSING_ERROR:
            self._set_rejected_ui(True)
        elif self._clip.status in {ClipStatus.UNSCHEDULED_YOUTUBE, ClipStatus.DELETED_YOUTUBE}:
            self._approve_btn.setEnabled(False)
            self._approve_btn.setStyleSheet("background-color: #444444; color: #888888;")

        hint = QLabel(
            "Atalhos (fora de campos de texto): Space = play/pause | A = aprovar | R = rejeitar\n"
            "[ = marcar início na posição atual  |  ] = marcar fim na posição atual"
        )
        hint.setStyleSheet("color: #888; font-size: 10px;")
        hint.setWordWrap(True)
        right.addWidget(hint)

        root.addLayout(right, 2)

        # Media player
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(1.5)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.setVideoOutput(self._video_item)
        self._player.positionChanged.connect(self._update_pos)
        self._player.positionChanged.connect(self._check_loop)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state)

        # Face detection para overlay 9:16
        self._face_detected.connect(self._on_face_detected, Qt.ConnectionType.QueuedConnection)

    def _make_video_link(self) -> QLabel:
        video = self._service.get_video(self._clip.video_id)
        title = video.title if video else self._clip.video_id
        url = f"https://www.youtube.com/watch?v={self._clip.video_id}"
        label = QLabel(f'<a href="{url}">{title}</a>')
        label.setOpenExternalLinks(False)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        label.linkActivated.connect(lambda _: QDesktopServices.openUrl(QUrl(url)))
        return label

    # ── Carregamento do vídeo-fonte ───────────────────────────────────

    def _load_source_video(self) -> None:
        """Carrega o vídeo-fonte (não o render final) para preview instantâneo."""
        video = self._service.get_video(self._clip.video_id)
        source_path = Path(video.video_path) if (video and video.video_path) else None

        if not source_path or not source_path.exists():
            self._gfx_view.setVisible(False)
            self._no_video_label.setVisible(True)
            return

        self._gfx_view.setVisible(True)
        self._no_video_label.setVisible(False)

        # Detecta AV1 antes de carregar — QMediaPlayer pode não suportar
        try:
            from canal_soberania.utils.ffmpeg import probe
            data = probe(source_path)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video" and stream.get("codec_name") == "av1":
                    self._gfx_view.setVisible(False)
                    self._no_video_label.setText(
                        "Codec AV1 detectado: preview indisponível neste sistema.\n"
                        "Use o render final para conferir o resultado."
                    )
                    self._no_video_label.setVisible(True)
                    return
        except Exception:
            pass

        self._player.setSource(QUrl.fromLocalFile(str(source_path)))
        self._play_btn.setEnabled(True)
        # Salta para start_s assim que o player estiver pronto
        self._player.mediaStatusChanged.connect(self._on_media_ready)

        # Detecta rosto em background para posicionar o overlay
        threading.Thread(
            target=self._run_face_detection, args=(source_path,), daemon=True
        ).start()

    def _on_media_ready(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (
            QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.LoadedMedia,
        ):
            self._player.mediaStatusChanged.disconnect(self._on_media_ready)
            self._player.setPosition(self._loop_start_ms)
            # Ajusta tamanho natural do vídeo para o overlay
            size = self._video_item.nativeSize()
            if size.isValid():
                self._vid_natural_w = int(size.width())
                self._vid_natural_h = int(size.height())
                self._update_mask_center()
            self._fit_video()

    def _fit_video(self) -> None:
        """Ajusta o QGraphicsVideoItem para preencher o QGraphicsView."""
        vp = self._gfx_view.viewport()
        vp_w = vp.width()
        vp_h = vp.height()
        self._video_item.setSize(QSizeF(vp_w, vp_h))
        self._scene.setSceneRect(0, 0, vp_w, vp_h)
        self._update_mask_geometry(vp_w, vp_h)

    def resizeEvent(self, event: object) -> None:  # type: ignore[override]
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._fit_video()

    # ── Overlay 9:16 ─────────────────────────────────────────────────

    def _run_face_detection(self, path: Path) -> None:
        try:
            from canal_soberania.utils.reframe import detect_face_crop_x
            crop_x = detect_face_crop_x(path, sample_time=self._clip.start_s + 2.0)
        except Exception:
            crop_x = None
        self._face_detected.emit(crop_x)

    def _on_face_detected(self, crop_x: object) -> None:
        if self._vid_natural_w > 0:
            cx = crop_x if isinstance(crop_x, int) else (self._vid_natural_w - int(self._vid_natural_h * 9 / 16)) // 2
            self._face_crop_x = cx
        else:
            self._face_crop_x = None
        self._update_mask_center()

    def _update_mask_center(self) -> None:
        if self._vid_natural_w <= 0 or self._vid_natural_h <= 0:
            return
        crop_x = getattr(self, "_face_crop_x", None)
        if crop_x is None:
            crop_x = (self._vid_natural_w - int(self._vid_natural_h * 9 / 16)) // 2
        vp = self._gfx_view.viewport()
        self._update_mask_geometry(vp.width(), vp.height(), src_crop_x=crop_x)

    def _update_mask_geometry(
        self, vp_w: int, vp_h: int, src_crop_x: int | None = None
    ) -> None:
        if self._vid_natural_w <= 0:
            return
        if src_crop_x is None:
            src_crop_x = getattr(self, "_face_crop_x", None)
            if src_crop_x is None:
                src_crop_x = (self._vid_natural_w - int(self._vid_natural_h * 9 / 16)) // 2
        # Escala crop_x para coordenadas do viewport
        scale_x = vp_w / self._vid_natural_w
        scale_y = vp_h / self._vid_natural_h
        scaled_crop_x = src_crop_x * scale_x
        scaled_crop_w = int(self._vid_natural_h * 9 / 16) * scale_x
        self._mask.set_viewport(float(vp_w), float(vp_h), scaled_crop_x)
        _ = scale_y  # usado indiretamente via vp_h proporcional

    # ── Reprodução ────────────────────────────────────────────────────

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_state(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("⏸ Pause")
        else:
            self._play_btn.setText("▶ Play")

    def _on_duration_changed(self, ms: int) -> None:
        self._seek_bar.setRange(0, ms)
        self._seek_bar.setEnabled(ms > 0)
        self._seek_bar.set_bounds(self._loop_start_ms, self._loop_end_ms, ms)
        self._update_pos(self._player.position())

    def _on_seek(self, ms: int) -> None:
        self._player.setPosition(ms)

    def _update_pos(self, ms: int) -> None:
        if not self._seek_bar.isSliderDown():
            self._seek_bar.setValue(ms)
        dur = self._player.duration()
        self._pos_label.setText(f"{self._fmt(ms)} / {self._fmt(dur)}")

    def _check_loop(self, ms: int) -> None:
        if self._loop_end_ms > 0 and ms >= self._loop_end_ms:
            self._player.setPosition(self._loop_start_ms)

    @staticmethod
    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    # ── Loop A↔B em tempo real ────────────────────────────────────────

    def _on_trim_changed(self) -> None:
        """Debounce: espera 200ms parado antes de atualizar os limites do loop."""
        self._debounce_timer.start()

    def _refresh_loop_bounds(self) -> None:
        start_ms = int(self._start_spin.value() * 1000)
        end_ms = int(self._end_spin.value() * 1000)
        self._loop_start_ms = start_ms
        self._loop_end_ms = end_ms
        dur = self._player.duration()
        self._seek_bar.set_bounds(start_ms, end_ms, dur)
        # Se posição atual estiver fora do novo intervalo, salta para o início
        pos = self._player.position()
        if pos < start_ms or pos >= end_ms:
            self._player.setPosition(start_ms)

    # ── Atalhos de teclado ────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        focused = self.focusWidget()
        typing = isinstance(focused, (QTextEdit, QLineEdit, QDoubleSpinBox))
        if not typing:
            key = event.key()
            if key == Qt.Key.Key_Space:
                self._toggle_play()
                return
            elif key == Qt.Key.Key_A:
                self._approve()
                return
            elif key == Qt.Key.Key_R:
                self._toggle_reject()
                return
            elif key == Qt.Key.Key_BracketLeft:
                self._start_spin.setValue(self._player.position() / 1000.0)
                return
            elif key == Qt.Key.Key_BracketRight:
                self._end_spin.setValue(self._player.position() / 1000.0)
                return
        super().keyPressEvent(event)

    # ── Persistência ─────────────────────────────────────────────────

    def _save_changes(self, *, silent: bool = False) -> None:
        hook = self._hook_te.toPlainText().strip() or None
        payoff = self._payoff_te.toPlainText().strip() or None
        title = self._title_edit.text().strip() or None
        description = self._description_te.toPlainText().strip() or None
        tags_raw = self._tags_edit.text().strip()
        tags: list[str] | None = (
            [t.strip() for t in tags_raw.split(",") if t.strip()][:15]
            if tags_raw else None
        )
        schedule: str | None = (
            self._schedule_dt.dateTime().toString("yyyy-MM-ddTHH:mm:00")
            if self._schedule_chk.isChecked()
            else None
        )
        render_v = self._render_vertical_chk.isChecked()
        render_h = self._render_horizontal_chk.isChecked()

        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._service.update_clip_text(
                self._clip.clip_id, hook, payoff, title, schedule, render_v, render_h,
                description=description, tags=tags,
            )
            self._clip = self._clip.model_copy(update={
                "hook": hook, "payoff": payoff, "title": title,
                "description": description,
                "tags": tags if tags is not None else self._clip.tags,
                "youtube_publish_at": schedule,
                "render_vertical": render_v, "render_horizontal": render_h,
            })
            if not silent:
                self._save_btn.setText("✓ Salvo")
                self._save_btn.setStyleSheet("color: #2e7d32; font-weight: bold;")
                QTimer.singleShot(2000, self._reset_save_btn)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _reset_save_btn(self) -> None:
        self._save_btn.setText("Salvar alterações")
        self._save_btn.setStyleSheet("")

    def _apply_trim(self) -> None:
        start = self._start_spin.value()
        end = self._end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "Trim inválido", "O fim deve ser maior que o início.")
            return
        try:
            self._service.update_clip_trim(self._clip.clip_id, start, end)
            QMessageBox.information(
                self,
                "Trim salvo",
                f"Trim salvo: {start:.1f}s → {end:.1f}s\n"
                "O clipe será re-renderizado na próxima execução do pipeline.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erro", str(exc))

    # ── Aprovação / rejeição ──────────────────────────────────────────

    def _on_burned_subs_toggled(self, checked: bool) -> None:
        count = self._service.mark_video_burned_subtitles(self._clip.video_id, checked)
        if checked and count > 0:
            QMessageBox.information(
                self,
                "Legenda queimada marcada",
                f"{count} clipe(s) deste vídeo foram re-enfileirados para edição sem legenda.\n"
                "Os clipes serão re-renderizados automaticamente.",
            )

    def _approve(self) -> None:
        self._save_changes(silent=True)
        if self._clip.status == ClipStatus.METADATA_READY:
            self._confirm_and_publish()
        else:
            try:
                self._service.approve_clip(self._clip.clip_id)
                self.accept()
            except Exception as exc:
                QMessageBox.critical(self, "Erro ao aprovar", str(exc))

    def _confirm_and_publish(self) -> None:
        clip = self._service.get_clip(self._clip.clip_id) or self._clip
        title_str = clip.title or "(sem título)"
        tags_str = ", ".join(clip.tags[:10]) if clip.tags else "(sem tags)"
        desc = clip.description or ""
        desc_preview = desc[:_DESC_PREVIEW_LEN] + ("…" if len(desc) > _DESC_PREVIEW_LEN else "")

        msg = QMessageBox(self)
        msg.setWindowTitle("Confirmar publicação no YouTube")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText("<b>Liberar este clipe para publicação?</b>")
        msg.setInformativeText(
            f"<b>Título:</b> {title_str}<br><br>"
            f"<b>Tags:</b> {tags_str}<br><br>"
            f"<b>Descrição (início):</b><br>{desc_preview}"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        msg.button(QMessageBox.StandardButton.Ok).setText("Liberar para publicação")
        msg.button(QMessageBox.StandardButton.Cancel).setText("Cancelar")

        if msg.exec() == QMessageBox.StandardButton.Ok:
            try:
                self._service.approve_clip(self._clip.clip_id)
                self.published = True
                self.accept()
            except Exception as exc:
                QMessageBox.critical(self, "Erro ao liberar", str(exc))

    def _do_unschedule(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._service.unschedule_clip(self._clip.clip_id)
            self._clip = self._clip.model_copy(update={
                "status": ClipStatus.UNSCHEDULED_YOUTUBE, "youtube_publish_at": None,
            })
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao cancelar agendamento", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        if self._unschedule_btn:
            self._unschedule_btn.setEnabled(False)
        if self._discard_btn:
            self._discard_btn.setEnabled(False)
        self._approve_btn.setEnabled(False)
        self._approve_btn.setStyleSheet("background-color: #444444; color: #888888;")
        self._start_spin.setEnabled(True)
        self._end_spin.setEnabled(True)
        self._apply_trim_btn.setEnabled(True)
        self._schedule_chk.setChecked(False)

    def _do_discard(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Confirmar descarte",
            "Deletar o vídeo do YouTube é irreversível.\n\nDeseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._service.discard_clip(self._clip.clip_id)
            self._clip = self._clip.model_copy(update={
                "status": ClipStatus.DELETED_YOUTUBE, "youtube_id": None, "youtube_id_horizontal": None,
            })
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao descartar", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.accept()

    def _toggle_reject(self) -> None:
        if self._clip.status == ClipStatus.PROCESSING_ERROR:
            try:
                self._service.restore_clip(self._clip.clip_id)
                self._clip = self._clip.model_copy(update={"status": ClipStatus.IDENTIFIED})
                self._set_rejected_ui(False)
            except Exception as exc:
                QMessageBox.critical(self, "Erro ao restaurar", str(exc))
        else:
            try:
                self._service.reject_clip(self._clip.clip_id, "Rejeitado manualmente via GUI")
                self._clip = self._clip.model_copy(update={"status": ClipStatus.PROCESSING_ERROR})
                self._set_rejected_ui(True)
            except Exception as exc:
                QMessageBox.critical(self, "Erro ao rejeitar", str(exc))

    def _set_rejected_ui(self, rejected: bool) -> None:
        if rejected:
            self._reject_btn.setText("Rejeitado ✓")
            self._reject_btn.setStyleSheet("background-color: #555555; color: #cccccc;")
            self._reject_btn.setToolTip("Clique para desfazer a rejeição")
            self._approve_btn.setEnabled(False)
            self._approve_btn.setStyleSheet("background-color: #444444; color: #888888;")
        else:
            self._reject_btn.setText("Rejeitar")
            self._reject_btn.setStyleSheet("background-color: #b71c1c; color: white;")
            self._reject_btn.setToolTip("")
            self._approve_btn.setEnabled(True)
            self._approve_btn.setStyleSheet("background-color: #2e7d32; color: white;")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._player.stop()
        self._debounce_timer.stop()
        super().closeEvent(event)
