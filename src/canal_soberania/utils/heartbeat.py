"""HeartbeatKeeper — mantém processing_since atualizado durante operações longas."""

from __future__ import annotations

import sqlite3
import threading
from types import TracebackType
from typing import Literal


class HeartbeatKeeper:
    """Context manager que atualiza `processing_since` a cada `interval` segundos.

    Uso:
        with HeartbeatKeeper(conn, "videos", "video_id", video_id):
            operacao_longa()
        # ao sair: processing_since = NULL (indica que terminou)

    Se o processo morrer dentro do bloco, processing_since fica com o último
    timestamp escrito. O pipeline detecta heartbeats com mais de 3 min e reseta
    o item para reprocessamento.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        table: Literal["videos", "clips"],
        id_col: str,
        row_id: str,
        interval: int = 60,
    ) -> None:
        self._conn = conn
        self._table = table
        self._id_col = id_col
        self._row_id = row_id
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _beat(self) -> None:
        self._conn.execute(
            f"UPDATE {self._table} SET processing_since = datetime('now') WHERE {self._id_col} = ?",  # noqa: S608
            (self._row_id,),
        )
        self._conn.commit()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._beat()
            except Exception:
                pass

    def __enter__(self) -> "HeartbeatKeeper":
        try:
            self._beat()
        except Exception:
            pass
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 2)
        try:
            self._conn.execute(
                f"UPDATE {self._table} SET processing_since = NULL WHERE {self._id_col} = ?",  # noqa: S608
                (self._row_id,),
            )
            self._conn.commit()
        except Exception:
            pass
