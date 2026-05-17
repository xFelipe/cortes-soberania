"""Bridge entre o EventBus do pipeline e o sistema de signals/slots do Qt.

O pipeline publica eventos a partir de QThread (thread de trabalho). O Qt exige
que atualizações de UI sejam feitas na thread principal. Ao emitir um Signal de
uma thread secundária, o Qt enfileira a entrega automaticamente via event loop —
sem necessidade de invokeMethod manual.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from canal_soberania.core.events import EventBus, PipelineEvent


class EventBridge(QObject):
    """Retransmite PipelineEvent do EventBus como Qt Signal thread-safe."""

    event_received = Signal(str, dict)  # (event_type, payload)

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = bus
        bus.subscribe("*", self._relay)

    def _relay(self, event: PipelineEvent) -> None:
        self.event_received.emit(event.type, event.payload)

    def detach(self) -> None:
        """Remove o handler do bus (usar ao fechar a janela)."""
        self._bus.unsubscribe("*", self._relay)
