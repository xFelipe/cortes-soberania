"""Widget de log em tempo real do pipeline com botões de stage."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_STAGE_BUTTONS: list[tuple[str, str]] = [
    ("Discover", "run_discover"),
    ("Triage Metadata", "run_triage_metadata"),
    ("Triage Caption", "run_triage_caption"),
    ("Download", "run_download"),
    ("Transcribe", "run_transcribe"),
    ("Triage Transcript", "run_triage_transcript"),
    ("Find Clips", "run_find_clips"),
    ("Edit", "run_edit"),
    ("Thumbnail", "run_thumbnail"),
    ("Metadata", "run_generate_metadata"),
    ("Upload YouTube", "run_upload_youtube"),
    ("Upload TikTok", "run_upload_tiktok"),
]

_EVENT_COLORS: dict[str, str] = {
    "stage_started": "#1565c0",
    "stage_completed": "#2e7d32",
    "stage_error": "#b71c1c",
    "stage_will_retry": "#e65100",
    "stage_cancelled": "#757575",
    "clip_approved": "#00695c",
    "clip_rejected": "#b71c1c",
    "clip_trim_updated": "#4a148c",
}


class PipelineLog(QWidget):
    """Painel de controle: botões de stage + log de eventos em tempo real."""

    def __init__(self, run_stage_callback: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._run_cb = run_stage_callback
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Botões de stage
        group = QGroupBox("Executar Stage")
        grid = QGridLayout(group)
        cols = 4
        for idx, (label, stage_id) in enumerate(_STAGE_BUTTONS):
            btn = QPushButton(label)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _checked=False, s=stage_id: self._run_cb(s))
            grid.addWidget(btn, idx // cols, idx % cols)
        layout.addWidget(group)

        # Botão cancelar
        cancel_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancelar pipeline")
        self._cancel_btn.setStyleSheet("background-color: #b71c1c; color: white;")
        cancel_row.addStretch()
        cancel_row.addWidget(self._cancel_btn)
        layout.addLayout(cancel_row)

        # Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self._log)

    def connect_cancel(self, slot: Callable[[], None]) -> None:
        self._cancel_btn.clicked.connect(slot)

    def append_event(self, event_type: str, payload: dict) -> None:  # type: ignore[type-arg]
        ts = datetime.now().strftime("%H:%M:%S")
        color = _EVENT_COLORS.get(event_type, "#cccccc")
        stage = payload.get("stage", "")
        error = payload.get("error", "")
        msg = f"[{ts}] {event_type}"
        if stage:
            msg += f" — {stage}"
        if error:
            msg += f": {error}"

        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.insertText(msg + "\n", fmt)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    def clear_log(self) -> None:
        self._log.clear()
