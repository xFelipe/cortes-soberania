"""Dialog para adicionar um vídeo manualmente ao pipeline via URL ou ID."""

from __future__ import annotations

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QThread,
    QVBoxLayout,
)

from canal_soberania.models import Video
from canal_soberania.services.pipeline_service import PipelineService

_YT_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|/shorts/|/embed/|/v/)([A-Za-z0-9_-]{11})"
    r"|^([A-Za-z0-9_-]{11})$"
)


def _extract_video_id(text: str) -> str | None:
    m = _YT_ID_RE.search(text.strip())
    if not m:
        return None
    return m.group(1) or m.group(2)


class _Worker(QThread):
    success: Signal = Signal(object)   # Video
    error: Signal = Signal(str)

    def __init__(self, service: PipelineService, video_id: str, parent: QThread | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._video_id = video_id

    def run(self) -> None:
        try:
            video: Video = self._service.add_video_by_id(self._video_id)
            self.success.emit(video)
        except Exception as exc:
            self.error.emit(str(exc))


class AddVideoDialog(QDialog):
    """Janela modal para adicionar um vídeo ao pipeline via URL ou ID do YouTube."""

    video_added = Signal(str)   # video_id adicionado com sucesso

    def __init__(self, service: PipelineService, parent: object = None) -> None:
        super().__init__(parent)  # type: ignore[call-overload]
        self._service = service
        self._worker: _Worker | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Adicionar vídeo")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("URL do YouTube ou ID do vídeo (11 caracteres):"))

        self._input = QLineEdit()
        self._input.setPlaceholderText("https://youtube.com/watch?v=... ou dQw4w9WgXcQ")
        self._input.returnPressed.connect(self._on_add)
        layout.addWidget(self._input)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #b71c1c;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self._add_btn = QPushButton("Adicionar")
        self._add_btn.setDefault(True)
        self._add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(self._add_btn)
        layout.addLayout(btn_row)

    def _on_add(self) -> None:
        text = self._input.text().strip()
        if not text:
            return

        video_id = _extract_video_id(text)
        if video_id is None:
            self._show_error(
                "Não foi possível extrair o ID do vídeo.\n"
                "Cole a URL completa (youtube.com/watch?v=… ou youtu.be/…) "
                "ou o ID de 11 caracteres."
            )
            return

        self._add_btn.setEnabled(False)
        self._add_btn.setText("Buscando…")
        self._error_label.hide()

        self._worker = _Worker(self._service, video_id, self)
        self._worker.success.connect(self._on_success)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_success(self, video: Video) -> None:
        self.video_added.emit(video.video_id)
        QMessageBox.information(
            self,
            "Vídeo adicionado",
            f'"{video.title}"\nfoi adicionado ao pipeline com status \'discovered\'.',
        )
        self.accept()

    def _on_error(self, msg: str) -> None:
        self._add_btn.setEnabled(True)
        self._add_btn.setText("Adicionar")
        self._show_error(msg)

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
        self.adjustSize()
