"""Diálogo de review de clipes: player de preview + aprovação/rejeição/trim."""

from __future__ import annotations

import subprocess
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices, QKeyEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
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

from canal_soberania.models import Clip
from canal_soberania.services.pipeline_service import PipelineService

_DESC_PREVIEW_LEN = 300


class _SeekSlider(QSlider):
    """QSlider que pula direto para o ponto clicado em vez de avançar um page step."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(event.position().x()), self.width()
            )
            self.setValue(val)
            self.sliderMoved.emit(val)
        super().mousePressEvent(event)


class ClipReviewDialog(QDialog):
    """Abre um clipe para review: player, edição de textos, trim e aprovação.

    Atalhos (fora de campos de texto): Space = play/pause | A = aprovar | R = rejeitar
    """

    _boost_ready = Signal(str)  # path do arquivo com áudio amplificado, ou "" se falhou

    def __init__(
        self, clip: Clip, service: PipelineService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._clip = clip
        self._service = service
        self._boost_cancelled = False
        self.published = False  # True se o clipe foi liberado para publicação
        self.setWindowTitle(f"Review — {clip.clip_id}")
        self.resize(960, 700)
        self._setup_ui()
        self._load_video()

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)

        # ── Esquerda: player ──────────────────────────────────────────
        left = QVBoxLayout()

        self._video_widget = QVideoWidget()
        self._video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._video_widget.setMinimumSize(480, 360)
        left.addWidget(self._video_widget)

        self._seek_bar = _SeekSlider(Qt.Orientation.Horizontal)
        self._seek_bar.setRange(0, 0)
        self._seek_bar.setEnabled(False)
        self._seek_bar.sliderMoved.connect(self._on_seek)
        left.addWidget(self._seek_bar)

        ctrl = QHBoxLayout()
        self._play_btn = QPushButton("▶ Play")
        self._play_btn.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._play_btn)
        self._pos_label = QLabel("0:00 / 0:00")
        ctrl.addWidget(self._pos_label)
        ctrl.addStretch()
        left.addLayout(ctrl)

        self._no_video_label = QLabel("Arquivo de vídeo não encontrado.\nRode o stage Edit primeiro.")
        self._no_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_video_label.setVisible(False)
        left.addWidget(self._no_video_label)

        root.addLayout(left, 3)

        # ── Direita: info + textos editáveis + trim + ações ──────────
        right = QVBoxLayout()

        # Info (somente leitura)
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

        # Textos editáveis: título, hook, payoff, descrição, tags
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

        # Agendamento de publicação
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
            dt = QDateTime.fromString(self._clip.youtube_publish_at[:16], "yyyy-MM-ddTHH:mm")
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

        # Formatos de saída
        is_scheduled = self._clip.status in {"scheduled_youtube", "uploaded_youtube",
                                             "uploading_youtube"}
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

        # Trim (bloqueado enquanto clipe está agendado/publicado)
        trim_group = QGroupBox("Editar trim")
        trim_layout = QFormLayout(trim_group)
        self._start_spin = QDoubleSpinBox()
        self._start_spin.setRange(0, 86400)
        self._start_spin.setDecimals(1)
        self._start_spin.setSuffix(" s")
        self._start_spin.setValue(self._clip.start_s)
        trim_layout.addRow("Início:", self._start_spin)
        self._end_spin = QDoubleSpinBox()
        self._end_spin.setRange(0, 86400)
        self._end_spin.setDecimals(1)
        self._end_spin.setSuffix(" s")
        self._end_spin.setValue(self._clip.end_s)
        trim_layout.addRow("Fim:", self._end_spin)
        self._apply_trim_btn = QPushButton("Aplicar trim")
        self._apply_trim_btn.clicked.connect(self._apply_trim)
        trim_layout.addRow(self._apply_trim_btn)
        if is_scheduled:
            self._start_spin.setEnabled(False)
            self._end_spin.setEnabled(False)
            self._apply_trim_btn.setEnabled(False)
            trim_group.setToolTip("Cancele o agendamento primeiro para alterar o corte.")
        right.addWidget(trim_group)

        right.addStretch()

        # Botões — layout condicional por status
        btn_box = QDialogButtonBox()
        approve_label = (
            "Liberar para publicação" if self._clip.status == "metadata_ready" else "Aprovar etapa"
        )
        self._approve_btn = btn_box.addButton(approve_label, QDialogButtonBox.ButtonRole.AcceptRole)
        self._approve_btn.setStyleSheet("background-color: #2e7d32; color: white;")
        self._approve_btn.clicked.connect(self._approve)

        self._unschedule_btn: QPushButton | None = None
        self._discard_btn: QPushButton | None = None

        if self._clip.status in {"scheduled_youtube", "uploaded_youtube", "uploading_youtube"}:
            # Dois botões de remoção para clipes já no YouTube
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

            self._reject_btn = self._discard_btn  # alias para o atalho R
        else:
            self._reject_btn = btn_box.addButton("Rejeitar", QDialogButtonBox.ButtonRole.RejectRole)
            self._reject_btn.setStyleSheet("background-color: #b71c1c; color: white;")
            self._reject_btn.clicked.connect(self._toggle_reject)

        close_btn = btn_box.addButton("Fechar", QDialogButtonBox.ButtonRole.DestructiveRole)
        close_btn.clicked.connect(self.reject)
        right.addWidget(btn_box)

        # Inicializa estado dos botões conforme status atual do clipe
        if self._clip.status == "processing_error":
            self._set_rejected_ui(True)
        elif self._clip.status in {"unscheduled_youtube", "deleted_youtube"}:
            self._approve_btn.setEnabled(False)
            self._approve_btn.setStyleSheet("background-color: #444444; color: #888888;")

        hint = QLabel(
            "Atalhos (fora de campos de texto): Space = play/pause | A = aprovar | R = rejeitar"
        )
        hint.setStyleSheet("color: #888; font-size: 10px;")
        hint.setWordWrap(True)
        right.addWidget(hint)

        root.addLayout(right, 2)

        # Media player
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(1.0)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.setVideoOutput(self._video_widget)
        self._player.positionChanged.connect(self._update_pos)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state)

    def _on_burned_subs_toggled(self, checked: bool) -> None:
        count = self._service.mark_video_burned_subtitles(self._clip.video_id, checked)
        if checked and count > 0:
            QMessageBox.information(
                self,
                "Legenda queimada marcada",
                f"{count} clipe(s) deste vídeo foram re-enfileirados para edição sem legenda.\n"
                "Rode o stage Edit para re-renderizar.",
            )

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

    # ── Reprodução ────────────────────────────────────────────────────

    def _load_video(self) -> None:
        self._temp_preview: Path | None = None
        path = self._clip.clip_path_vertical
        if path and Path(path).exists():
            self._video_widget.setVisible(True)
            self._no_video_label.setVisible(False)
            self._play_btn.setEnabled(False)
            self._play_btn.setText("⏳ Preparando áudio…")
            self._boost_ready.connect(self._on_boost_ready, Qt.ConnectionType.QueuedConnection)
            threading.Thread(target=self._run_boost, args=(path,), daemon=True).start()
        else:
            self._video_widget.setVisible(False)
            self._no_video_label.setVisible(True)
            self._play_btn.setEnabled(False)

    def _run_boost(self, source: str) -> None:
        """Executa em thread de fundo — amplifica áudio via ffmpeg."""
        with tempfile.NamedTemporaryFile(suffix="_preview.mp4", delete=False) as _f:
            tmp = Path(_f.name)
        try:
            cmd = ["ffmpeg", "-i", source, "-af", "volume=8dB", "-c:v", "copy", "-y", str(tmp)]  # noqa: S607
            subprocess.run(cmd, capture_output=True, timeout=60, check=True)  # noqa: S603
            self._boost_ready.emit(str(tmp))
        except Exception:
            self._boost_ready.emit("")  # falha: thread principal usará arquivo original

    def _on_boost_ready(self, boosted_path: str) -> None:
        """Chamado na thread principal quando o ffmpeg termina."""
        if self._boost_cancelled:
            if boosted_path:
                Path(boosted_path).unlink(missing_ok=True)
            return
        original = self._clip.clip_path_vertical or ""
        if boosted_path:
            self._temp_preview = Path(boosted_path)
            self._player.setSource(QUrl.fromLocalFile(boosted_path))
        elif original:
            self._player.setSource(QUrl.fromLocalFile(original))
        self._play_btn.setEnabled(True)
        self._play_btn.setText("▶ Play")

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
        self._update_pos(self._player.position())

    def _on_seek(self, ms: int) -> None:
        self._player.setPosition(ms)

    def _update_pos(self, ms: int) -> None:
        if not self._seek_bar.isSliderDown():
            self._seek_bar.setValue(ms)
        dur = self._player.duration()
        self._pos_label.setText(f"{self._fmt(ms)} / {self._fmt(dur)}")

    @staticmethod
    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    # ── Atalhos de teclado ────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
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
                f"Trim atualizado: {start:.1f}s → {end:.1f}s\nRode o stage Edit para re-renderizar.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erro", str(exc))

    # ── Aprovação / rejeição ──────────────────────────────────────────

    def _approve(self) -> None:
        self._save_changes(silent=True)
        if self._clip.status == "metadata_ready":
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
        """Cancela o agendamento no YouTube (vídeo vira privado sem publishAt)."""
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._service.unschedule_clip(self._clip.clip_id)
            self._clip = self._clip.model_copy(update={
                "status": "unscheduled_youtube", "youtube_publish_at": None,
            })
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao cancelar agendamento", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        # Atualiza UI: desativa botões de plataforma, libera trim
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
        """Deleta o vídeo do YouTube permanentemente."""
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
                "status": "deleted_youtube", "youtube_id": None, "youtube_id_horizontal": None,
            })
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao descartar", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.accept()

    def _toggle_reject(self) -> None:
        """Alterna entre rejeitado e aguardando aprovação (sem fechar o diálogo)."""
        if self._clip.status == "processing_error":
            try:
                self._service.restore_clip(self._clip.clip_id)
                self._clip = self._clip.model_copy(update={"status": "identified"})
                self._set_rejected_ui(False)
            except Exception as exc:
                QMessageBox.critical(self, "Erro ao restaurar", str(exc))
        else:
            try:
                self._service.reject_clip(self._clip.clip_id, "Rejeitado manualmente via GUI")
                self._clip = self._clip.model_copy(update={"status": "processing_error"})
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

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._boost_cancelled = True
        self._player.stop()
        if getattr(self, "_temp_preview", None) and self._temp_preview.exists():
            self._temp_preview.unlink(missing_ok=True)
        super().closeEvent(event)
