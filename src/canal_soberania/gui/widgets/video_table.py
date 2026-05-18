"""Widget de tabela de vídeos com código de cores por status."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from canal_soberania.models import Video, VideoStatus

_STATUS_COLOR: dict[str, str] = {
    "discovered": "#555555",
    "triage_metadata_passed": "#2e7d32",
    "triage_metadata_rejected": "#b71c1c",
    "on_hold_metadata_passed": "#6a1e8a",
    "triage_caption_passed": "#1b5e20",
    "triage_caption_rejected": "#c62828",
    "triage_caption_skipped": "#4e342e",
    "downloading": "#f57f17",
    "downloaded": "#33691e",
    "transcribing": "#e65100",
    "transcribed": "#1a237e",
    "transcribe_error": "#b71c1c",
    "triage_transcript_passed": "#e65100",   # âmbar — aguarda aprovação manual
    "triage_transcript_rejected": "#880e4f",
    "approved_for_clips": "#004d40",          # verde escuro — aprovado, pipeline vai rodar
    "finding_clips": "#4a148c",
    "clips_found": "#1565c0",
    "processing_error": "#d50000",
}

def _sort_priority(status: str) -> int:
    if status == "triage_metadata_rejected":
        return 2
    if status in ("triage_caption_rejected", "triage_transcript_rejected", "transcribe_error", "processing_error"):
        return 1
    return 0


def _fmt_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return iso[:10]


_COLUMNS = ["Título", "Canal", "Status", "Duração", "Publicado"]

_LINK_COLOR = "#1565c0"
_URL_ROLE = Qt.ItemDataRole.UserRole + 1   # armazena URL clicável
_STATUS_ROLE = Qt.ItemDataRole.UserRole + 2  # armazena status bruto (sem spinner)

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_ACTIVE_STATUSES: frozenset[str] = frozenset({"downloading", "transcribing", "finding_clips"})


class VideoTable(QWidget):
    """Tabela de vídeos com filtro por status e seleção para ações."""

    video_selected = Signal(str)          # video_id (duplo clique)
    video_approve_requested = Signal(str)  # video_id
    video_reject_requested = Signal(str)   # video_id

    def __init__(
        self,
        canal_urls: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._videos: list[Video] = []
        self._canal_urls: dict[str, str] = canal_urls or {}
        self._spinner_frame: int = 0
        self._setup_ui()

        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(120)
        self._spinner_timer.timeout.connect(self._tick_spinner)
        self._spinner_timer.start()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Filtro por status
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtrar por status:"))
        self._status_filter = QComboBox()
        self._status_filter.addItem("Todos", None)
        for s in _STATUS_COLOR:
            self._status_filter.addItem(s, s)
        self._status_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._status_filter)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Tabela
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._table)

    def load(self, videos: list[Video]) -> None:
        self._videos = videos
        self._apply_filter()

    def _apply_filter(self) -> None:
        selected_status: str | None = self._status_filter.currentData()
        rows = (
            self._videos
            if selected_status is None
            else [v for v in self._videos if v.status == selected_status]
        )
        rows = sorted(rows, key=lambda v: _sort_priority(v.status))

        self._table.setRowCount(0)
        for video in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)

            video_url = f"https://www.youtube.com/watch?v={video.video_id}"

            # col 0: Título — link para o vídeo no YouTube; tooltip mostra o video_id
            item_title = QTableWidgetItem(video.title)
            item_title.setData(Qt.ItemDataRole.UserRole, video.video_id)
            item_title.setData(_URL_ROLE, video_url)
            item_title.setForeground(QColor(_LINK_COLOR))
            item_title.setToolTip(f"{video.video_id}  |  {video_url}")
            self._table.setItem(row, 0, item_title)

            # col 1: Canal — link para a página do canal
            channel_url = self._canal_urls.get(video.canal_id, "")
            item_canal = QTableWidgetItem(video.canal_id)
            item_canal.setData(Qt.ItemDataRole.UserRole, video.video_id)
            if channel_url:
                item_canal.setData(_URL_ROLE, channel_url)
                item_canal.setForeground(QColor(_LINK_COLOR))
                item_canal.setToolTip(channel_url)
            self._table.setItem(row, 1, item_canal)

            # col 2: status (com suporte a spinner animado)
            item_status = QTableWidgetItem(self._fmt_status(video.status))
            item_status.setData(Qt.ItemDataRole.UserRole, video.video_id)
            item_status.setData(_STATUS_ROLE, video.status)
            item_status.setForeground(QColor(_STATUS_COLOR.get(video.status, "#555555")))
            self._table.setItem(row, 2, item_status)

            # cols 3-4: duração, publicado
            for col, val in [(3, _fmt_duration(video.duration_s)), (4, _fmt_date(video.published_at))]:
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, video.video_id)
                self._table.setItem(row, col, item)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """Abre URL do vídeo (col 0) ou do canal (col 1) no browser, apenas se clicar sobre o texto."""
        if col not in (0, 1):
            return
        item = self._table.item(row, col)
        if item is None:
            return
        url: str = item.data(_URL_ROLE) or ""
        if not url:
            return
        cursor_pos = self._table.viewport().mapFromGlobal(QCursor.pos())
        item_rect = self._table.visualItemRect(item)
        text_width = self._table.fontMetrics().horizontalAdvance(item.text())
        if cursor_pos.x() <= item_rect.left() + 6 + text_width:
            QDesktopServices.openUrl(QUrl(url))

    def _on_double_click(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if item:
            self.video_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def _fmt_status(self, status: str) -> str:
        if status in _ACTIVE_STATUSES:
            return f"{_SPINNER_FRAMES[self._spinner_frame]}  {status}"
        return status

    def _tick_spinner(self) -> None:
        self._spinner_frame = (self._spinner_frame + 1) % len(_SPINNER_FRAMES)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 2)
            if item is None:
                continue
            status: str = item.data(_STATUS_ROLE) or ""
            if status in _ACTIVE_STATUSES:
                item.setText(self._fmt_status(status))

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._table.itemAt(pos)
        if item is None:
            return
        video_id: str = item.data(Qt.ItemDataRole.UserRole) or ""
        if not video_id:
            return

        menu = QMenu(self)
        approve_action = menu.addAction("✓ Aprovar")
        reject_action = menu.addAction("✗ Recusar")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen == approve_action:
            self.video_approve_requested.emit(video_id)
        elif chosen == reject_action:
            self.video_reject_requested.emit(video_id)
