"""QThread workers para executar stages do pipeline sem bloquear a UI."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal


class StageWorker(QThread):
    """Executa uma função do PipelineService em background thread.

    Usage:
        worker = StageWorker(service.run_discover)
        worker.finished.connect(on_done)
        worker.error.connect(on_error)
        worker.start()
    """

    finished = Signal()
    error = Signal(str)

    def __init__(self, fn: Callable[[], None], parent: QThread | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._fn = fn

    def run(self) -> None:
        try:
            self._fn()
            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))
