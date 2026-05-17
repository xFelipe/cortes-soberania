"""QThread workers para executar stages do pipeline sem bloquear a UI."""

from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from canal_soberania.services.pipeline_service import PipelineService


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


class PipelineLoopWorker(QThread):
    """Roda run_pipeline_auto em loop contínuo em background.

    A cada iteração: reseta itens travados → run_pipeline_auto → aguarda interval_s.
    O sleep é fracionado em blocos de 1 s para responder rapidamente ao stop().
    """

    iteration_done = Signal(int, int)  # (número da iteração, itens resetados)
    stage_error = Signal(str)          # mensagem de erro não-fatal

    def __init__(
        self,
        service: PipelineService,
        interval_s: int = 60,
        parent: QThread | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._service = service
        self._interval = interval_s
        self._active = True

    def stop(self) -> None:
        self._active = False
        self._service.cancel()

    def run(self) -> None:
        iteration = 0
        while self._active:
            iteration += 1
            stuck = (
                self._service.reset_stuck_videos()
                + self._service.reset_stuck_clips()
            )
            self._service.reset_cancel()
            try:
                self._service.run_pipeline_auto()
            except Exception as exc:
                self.stage_error.emit(str(exc))
            self.iteration_done.emit(iteration, stuck)

            # Sleep em blocos de 1 s para parar rapidamente ao fechar a janela
            for _ in range(self._interval):
                if not self._active:
                    break
                time.sleep(1)
