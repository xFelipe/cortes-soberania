"""Diálogo de review de clipes: player de preview + aprovação/rejeição/trim."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
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
    """Abre um clipe para review: player, info, trim e ações Aprovar/Rejeitar."""

    def __init__(
        self, clip: Clip, service: PipelineService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._clip = clip
        self._service = service
        self.setWindowTitle(f"Review — {clip.clip_id}")
        self.resize(900, 640)
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

        # Controles de reprodução
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

        # ── Direita: info + trim + ações ─────────────────────────────
        right = QVBoxLayout()

        # Info
        info_group = QGroupBox("Informações do clipe")
        info_layout = QFormLayout(info_group)
        info_layout.addRow("ID:", QLabel(self._clip.clip_id))
        info_layout.addRow("Vídeo:", QLabel(self._clip.video_id))
        info_layout.addRow("Status:", QLabel(self._clip.status))
        info_layout.addRow("Score viral:", QLabel(str(self._clip.score_viral or "—")))
        info_layout.addRow("Score relevância:", QLabel(str(self._clip.score_relevancia or "—")))
        info_layout.addRow("Tema:", QLabel(self._clip.tema_soberania or "—"))
        right.addWidget(info_group)

        # Hook / Payoff
        hook_group = QGroupBox("Hook / Payoff")
        hook_layout = QVBoxLayout(hook_group)
        hook_te = QTextEdit(self._clip.hook or "")
        hook_te.setReadOnly(True)
        hook_te.setMaximumHeight(60)
        hook_layout.addWidget(QLabel("Hook:"))
        hook_layout.addWidget(hook_te)
        payoff_te = QTextEdit(self._clip.payoff or "")
        payoff_te.setReadOnly(True)
        payoff_te.setMaximumHeight(60)
        hook_layout.addWidget(QLabel("Payoff:"))
        hook_layout.addWidget(payoff_te)
        right.addWidget(hook_group)

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

        # Botões principais
        btn_box = QDialogButtonBox()
        self._approve_btn = btn_box.addButton("Aprovar", QDialogButtonBox.ButtonRole.AcceptRole)
        self._approve_btn.setStyleSheet("background-color: #2e7d32; color: white;")
        self._reject_btn = btn_box.addButton("Rejeitar", QDialogButtonBox.ButtonRole.RejectRole)
        self._reject_btn.setStyleSheet("background-color: #b71c1c; color: white;")
        close_btn = btn_box.addButton("Fechar", QDialogButtonBox.ButtonRole.DestructiveRole)
        self._approve_btn.clicked.connect(self._approve)
        self._reject_btn.clicked.connect(self._reject)
        close_btn.clicked.connect(self.reject)
        right.addWidget(btn_box)

        root.addLayout(right, 2)

        # Media player
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(1.0)  # 100 % — padrão Qt pode ser 0 dependendo do sistema
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.setVideoOutput(self._video_widget)
        self._player.positionChanged.connect(self._update_pos)
        self._player.playbackStateChanged.connect(self._on_playback_state)

    def _load_video(self) -> None:
        path = self._clip.clip_path_vertical
        if path and Path(path).exists():
            self._player.setSource(QUrl.fromLocalFile(path))
            self._video_widget.setVisible(True)
            self._no_video_label.setVisible(False)
        else:
            self._video_widget.setVisible(False)
            self._no_video_label.setVisible(True)
            self._play_btn.setEnabled(False)

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

    def _apply_trim(self) -> None:
        start = self._start_spin.value()
        end = self._end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "Trim inválido", "O fim deve ser maior que o início.")
            return
        try:
            self._service.update_clip_trim(self._clip.clip_id, start, end)
            QMessageBox.information(self, "Trim salvo", f"Trim atualizado: {start:.1f}s → {end:.1f}s\nRode o stage Edit para re-renderizar.")
        except Exception as exc:
            QMessageBox.critical(self, "Erro", str(exc))

    def _approve(self) -> None:
        try:
            self._service.approve_clip(self._clip.clip_id)
            QMessageBox.information(self, "Aprovado", f"Clipe avançado para o próximo status.")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao aprovar", str(exc))

    def _reject(self) -> None:
        try:
            self._service.reject_clip(self._clip.clip_id, "Rejeitado manualmente via GUI")
            QMessageBox.information(self, "Rejeitado", "Clipe marcado como erro de processamento.")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao rejeitar", str(exc))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._player.stop()
        super().closeEvent(event)
