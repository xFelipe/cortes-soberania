"""Diálogo de review de clipes: player de preview + aprovação/rejeição/trim."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QKeyEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from canal_soberania.models import Clip
from canal_soberania.services.pipeline_service import PipelineService


class ClipReviewDialog(QDialog):
    """Abre um clipe para review: player, edição de textos, trim e aprovação.

    Atalhos (fora de campos de texto): Space = play/pause | A = aprovar | R = rejeitar
    """

    def __init__(
        self, clip: Clip, service: PipelineService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._clip = clip
        self._service = service
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

        ctrl = QHBoxLayout()
        self._play_btn = QPushButton("▶ Play")
        self._play_btn.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._play_btn)
        self._pos_label = QLabel("0s")
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
        right.addWidget(info_group)

        # Textos editáveis: título, hook, payoff
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

        save_btn = QPushButton("Salvar alterações")
        save_btn.clicked.connect(lambda: self._save_changes(silent=False))
        edit_layout.addRow(save_btn)

        right.addWidget(edit_group)

        # Trim
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
        apply_trim_btn = QPushButton("Aplicar trim")
        apply_trim_btn.clicked.connect(self._apply_trim)
        trim_layout.addRow(apply_trim_btn)
        right.addWidget(trim_group)

        right.addStretch()

        # Botões — label do Aprovar muda quando clip está pronto para publicar
        approve_label = (
            "Liberar para publicação" if self._clip.status == "metadata_ready" else "Aprovar etapa"
        )
        btn_box = QDialogButtonBox()
        self._approve_btn = btn_box.addButton(approve_label, QDialogButtonBox.ButtonRole.AcceptRole)
        self._approve_btn.setStyleSheet("background-color: #2e7d32; color: white;")
        self._reject_btn = btn_box.addButton("Rejeitar", QDialogButtonBox.ButtonRole.RejectRole)
        self._reject_btn.setStyleSheet("background-color: #b71c1c; color: white;")
        close_btn = btn_box.addButton("Fechar", QDialogButtonBox.ButtonRole.DestructiveRole)
        self._approve_btn.clicked.connect(self._approve)
        self._reject_btn.clicked.connect(self._reject)
        close_btn.clicked.connect(self.reject)
        right.addWidget(btn_box)

        hint = QLabel("Atalhos (fora de campos de texto): Space = play/pause | A = aprovar | R = rejeitar")
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
        self._player.playbackStateChanged.connect(self._on_playback_state)

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
            self._play_btn.setEnabled(False)
            self._play_btn.setText("⏳ Preparando…")
            boosted = self._boost_audio(path)
            self._temp_preview = boosted
            self._player.setSource(QUrl.fromLocalFile(str(boosted or path)))
            self._video_widget.setVisible(True)
            self._no_video_label.setVisible(False)
            self._play_btn.setEnabled(True)
            self._play_btn.setText("▶ Play")
        else:
            self._video_widget.setVisible(False)
            self._no_video_label.setVisible(True)
            self._play_btn.setEnabled(False)

    def _boost_audio(self, source: str) -> Path | None:
        """Cria cópia temporária do clipe com áudio amplificado (+8 dB) para review."""
        tmp = Path(tempfile.mktemp(suffix="_preview.mp4"))
        try:
            subprocess.run(
                [
                    "ffmpeg", "-i", source,
                    "-af", "volume=8dB",
                    "-c:v", "copy",
                    "-y", str(tmp),
                ],
                capture_output=True,
                timeout=60,
                check=True,
            )
            return tmp
        except Exception:
            return None

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

    def _update_pos(self, ms: int) -> None:
        self._pos_label.setText(f"{ms / 1000:.1f}s")

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
                self._reject()
                return
        super().keyPressEvent(event)

    # ── Persistência ─────────────────────────────────────────────────

    def _save_changes(self, *, silent: bool = False) -> None:
        hook = self._hook_te.toPlainText().strip()
        payoff = self._payoff_te.toPlainText().strip()
        title = self._title_edit.text().strip()
        try:
            self._service.update_clip_text(
                self._clip.clip_id,
                hook or None,
                payoff or None,
                title or None,
            )
            if not silent:
                QMessageBox.information(self, "Salvo", "Alterações salvas com sucesso.")
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))

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
        desc_preview = desc[:300] + ("…" if len(desc) > 300 else "")

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
                QMessageBox.information(self, "Liberado", "Clipe na fila de publicação (scheduled_youtube).")
                self.accept()
            except Exception as exc:
                QMessageBox.critical(self, "Erro ao liberar", str(exc))

    def _reject(self) -> None:
        try:
            self._service.reject_clip(self._clip.clip_id, "Rejeitado manualmente via GUI")
            QMessageBox.information(self, "Rejeitado", "Clipe marcado como erro de processamento.")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao rejeitar", str(exc))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._player.stop()
        if getattr(self, "_temp_preview", None) and self._temp_preview.exists():
            self._temp_preview.unlink(missing_ok=True)
        super().closeEvent(event)
