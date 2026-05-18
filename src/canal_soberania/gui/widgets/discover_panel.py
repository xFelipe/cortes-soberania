"""Painel completo da aba Discover: lista de canais + formulário de execução."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from canal_soberania.config import Canal
from canal_soberania.services.pipeline_service import PipelineService


class _DiscoverWorker(QThread):
    """Roda discover em background; emite resultado ou erro."""

    finished = Signal(int)   # nº vídeos inseridos
    error = Signal(str)

    def __init__(
        self,
        service: PipelineService,
        canal_ids: list[str] | None,
        janela_dias: int,
        max_videos: int,
        dry_run: bool,
        auto_triage: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._canal_ids = canal_ids
        self._janela_dias = janela_dias
        self._max_videos = max_videos
        self._dry_run = dry_run
        self._auto_triage = auto_triage

    def run(self) -> None:
        try:
            self._service.run_discover(
                dry_run=self._dry_run,
                canal_ids=self._canal_ids,
                janela_dias=self._janela_dias,
                max_videos=self._max_videos,
            )
            if self._auto_triage and not self._dry_run:
                self._service.run_triage_metadata(dry_run=False)
                self._service.run_triage_caption(dry_run=False)
            self.finished.emit(0)
        except Exception as exc:
            self.error.emit(str(exc))


class _AdhocWorker(QThread):
    """Roda discover ad-hoc em background."""

    finished = Signal(int)   # nº vídeos inseridos
    error = Signal(str)

    def __init__(
        self,
        service: PipelineService,
        handle: str,
        persist: bool,
        janela_dias: int,
        max_videos: int,
        dry_run: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._handle = handle
        self._persist = persist
        self._janela_dias = janela_dias
        self._max_videos = max_videos
        self._dry_run = dry_run

    def run(self) -> None:
        try:
            n = self._service.discover_adhoc(
                self._handle,
                persist=self._persist,
                janela_dias=self._janela_dias,
                max_videos=self._max_videos,
                dry_run=self._dry_run,
            )
            self.finished.emit(n)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Painel principal
# ---------------------------------------------------------------------------

_TOLS = {"desconhecida", "alta", "media", "baixa"}


class DiscoverPanel(QWidget):
    """Painel da aba Discover — gerencia canais e dispara discover com parâmetros."""

    canais_changed = Signal()   # emitido quando a lista muda (add/toggle/delete)

    def __init__(self, service: PipelineService, refresh_videos_cb: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._refresh_videos_cb = refresh_videos_cb
        self._worker: _DiscoverWorker | _AdhocWorker | None = None
        self._setup_ui()
        self._load_canais()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        splitter.addWidget(self._build_canais_panel())
        splitter.addWidget(self._build_run_panel())
        splitter.setSizes([460, 380])

    def _build_canais_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 4, 0)

        layout.addWidget(QLabel("<b>Canais monitorados</b>"))

        self._canais_table = QTableWidget()
        self._canais_table.setColumnCount(6)
        self._canais_table.setHorizontalHeaderLabels(
            ["Ativo", "Nome", "Handle", "Tema", "Peso", "Auto-pub"]
        )
        self._canais_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._canais_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._canais_table.setColumnWidth(0, 44)
        self._canais_table.setColumnWidth(1, 160)
        self._canais_table.setColumnWidth(2, 120)
        self._canais_table.setColumnWidth(3, 130)
        self._canais_table.setColumnWidth(4, 46)
        self._canais_table.setColumnWidth(5, 56)
        self._canais_table.verticalHeader().setVisible(False)
        self._canais_table.cellDoubleClicked.connect(lambda _r, _c: self._on_edit_canal())
        layout.addWidget(self._canais_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Adicionar canal")
        add_btn.clicked.connect(self._on_add_canal)
        btn_row.addWidget(add_btn)
        edit_btn = QPushButton("Editar")
        edit_btn.clicked.connect(self._on_edit_canal)
        btn_row.addWidget(edit_btn)
        del_btn = QPushButton("Remover")
        del_btn.clicked.connect(self._on_delete_canal)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return w

    def _build_run_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 0, 0, 0)

        # ── Parâmetros ──────────────────────────────────────────────────
        params_box = QGroupBox("Parâmetros do Discover")
        params_form = QFormLayout(params_box)

        self._spin_dias = QSpinBox()
        self._spin_dias.setRange(1, 365)
        self._spin_dias.setValue(7)
        self._spin_dias.setSuffix(" dias")
        params_form.addRow("Janela de busca:", self._spin_dias)

        self._spin_max = QSpinBox()
        self._spin_max.setRange(1, 500)
        self._spin_max.setValue(20)
        self._spin_max.setSuffix(" vídeos/canal")
        params_form.addRow("Máx. vídeos por canal:", self._spin_max)

        self._chk_dry = QCheckBox("Dry-run (preview, não grava)")
        params_form.addRow("", self._chk_dry)

        self._chk_triage = QCheckBox("Auto-disparar triagem após")
        params_form.addRow("", self._chk_triage)

        layout.addWidget(params_box)

        # ── Seleção de canais ────────────────────────────────────────────
        sel_box = QGroupBox("Canais a incluir nessa execução")
        sel_layout = QVBoxLayout(sel_box)

        self._canal_list = QListWidget()
        self._canal_list.setFixedHeight(140)
        sel_layout.addWidget(self._canal_list)

        row = QHBoxLayout()
        mark_all = QPushButton("Todos")
        mark_all.clicked.connect(lambda: self._set_all_checked(True))
        row.addWidget(mark_all)
        mark_none = QPushButton("Nenhum")
        mark_none.clicked.connect(lambda: self._set_all_checked(False))
        row.addWidget(mark_none)
        row.addStretch()
        sel_layout.addLayout(row)
        layout.addWidget(sel_box)

        # ── Botão principal ─────────────────────────────────────────────
        self._run_btn = QPushButton("▶  Rodar Discover")
        self._run_btn.setFixedHeight(36)
        self._run_btn.clicked.connect(self._on_run_discover)
        layout.addWidget(self._run_btn)

        # ── Canal ad-hoc ────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        adhoc_box = QGroupBox("Canal ad-hoc (não cadastrado)")
        adhoc_form = QFormLayout(adhoc_box)

        self._adhoc_input = QLineEdit()
        self._adhoc_input.setPlaceholderText("@handle ou https://youtube.com/@...")
        adhoc_form.addRow("Handle / URL:", self._adhoc_input)

        self._chk_persist = QCheckBox("Salvar canal na lista")
        adhoc_form.addRow("", self._chk_persist)

        self._adhoc_btn = QPushButton("Rodar só nesse canal")
        self._adhoc_btn.clicked.connect(self._on_run_adhoc)
        adhoc_form.addRow("", self._adhoc_btn)

        layout.addWidget(adhoc_box)

        # ── Log ─────────────────────────────────────────────────────────
        layout.addWidget(QLabel("Log:"))
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        layout.addWidget(self._log)

        return w

    # ------------------------------------------------------------------
    # Carregamento de dados
    # ------------------------------------------------------------------

    def _load_canais(self) -> None:
        canais = self._service.get_canais()
        self._canais_table.setRowCount(len(canais))

        # Salva referência para poder acessar os objetos por linha
        self._canais: list[Canal] = canais

        for row, canal in enumerate(canais):
            # Coluna 0: toggle ativo
            chk = QCheckBox()
            chk.setChecked(canal.ativo)
            chk.setStyleSheet("margin-left: 10px;")
            chk.stateChanged.connect(
                lambda state, cid=canal.id: self._on_toggle_ativo(cid, bool(state))
            )
            self._canais_table.setCellWidget(row, 0, chk)

            self._canais_table.setItem(row, 1, QTableWidgetItem(canal.nome))
            self._canais_table.setItem(row, 2, QTableWidgetItem(canal.handle))
            self._canais_table.setItem(row, 3, QTableWidgetItem(canal.tema_primario))
            self._canais_table.setItem(row, 4, QTableWidgetItem(str(canal.peso)))
            self._canais_table.setItem(row, 5, QTableWidgetItem("sim" if canal.auto_publish else "não"))

        self._rebuild_canal_list()

    def _rebuild_canal_list(self) -> None:
        """Recria a QListWidget de seleção de canais para o discover."""
        self._canal_list.clear()
        for canal in self._canais:
            if not canal.ativo:
                continue
            item = QListWidgetItem(canal.nome)
            item.setData(Qt.ItemDataRole.UserRole, canal.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._canal_list.addItem(item)

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._canal_list.count()):
            item = self._canal_list.item(i)
            if item:
                item.setCheckState(state)

    def _selected_canal_ids(self) -> list[str] | None:
        """Retorna IDs marcados ou None se todos estiverem marcados (= sem filtro)."""
        ids: list[str] = []
        total = self._canal_list.count()
        for i in range(total):
            item = self._canal_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        if len(ids) == total:
            return None  # todos = sem filtro
        return ids or None

    # ------------------------------------------------------------------
    # Ações de canal (CRUD)
    # ------------------------------------------------------------------

    def _on_add_canal(self) -> None:
        from canal_soberania.gui.windows.canal_edit_dialog import CanalEditDialog
        dlg = CanalEditDialog(parent=self)
        dlg.canal_saved.connect(self._save_canal)
        dlg.exec()

    def _on_edit_canal(self) -> None:
        row = self._canais_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selecione um canal", "Clique em uma linha da tabela.")
            return
        canal = self._canais[row]
        from canal_soberania.gui.windows.canal_edit_dialog import CanalEditDialog
        dlg = CanalEditDialog(canal=canal, parent=self)
        dlg.canal_saved.connect(self._save_canal)
        dlg.exec()

    def _on_delete_canal(self) -> None:
        row = self._canais_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selecione um canal", "Clique em uma linha da tabela.")
            return
        canal = self._canais[row]
        confirm = QMessageBox.question(
            self,
            "Confirmar remoção",
            f'Remover canal "{canal.nome}" da lista?\n'
            "Os vídeos já coletados permanecem no banco.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_canal(canal.id)
        except Exception as exc:
            QMessageBox.warning(self, "Erro", str(exc))
            return
        self._load_canais()
        self.canais_changed.emit()

    @Slot(object)
    def _save_canal(self, canal: Canal) -> None:
        try:
            self._service.upsert_canal(canal)
        except Exception as exc:
            QMessageBox.warning(self, "Erro ao salvar", str(exc))
            return
        self._load_canais()
        self.canais_changed.emit()

    def _on_toggle_ativo(self, canal_id: str, ativo: bool) -> None:
        try:
            self._service.toggle_canal_ativo(canal_id, ativo)
        except Exception as exc:
            QMessageBox.warning(self, "Erro", str(exc))
            return
        # Rebuildamos só a lista de seleção (checkbox já foi atualizado pelo widget)
        idx = next((i for i, c in enumerate(self._canais) if c.id == canal_id), None)
        if idx is not None:
            self._canais[idx] = self._canais[idx].model_copy(update={"ativo": ativo})
        self._rebuild_canal_list()

    # ------------------------------------------------------------------
    # Execução do discover
    # ------------------------------------------------------------------

    def _on_run_discover(self) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "Ocupado", "Aguarde o discover atual terminar.")
            return

        canal_ids = self._selected_canal_ids()
        janela = self._spin_dias.value()
        max_v = self._spin_max.value()
        dry = self._chk_dry.isChecked()
        triage = self._chk_triage.isChecked()

        self._log_append(
            f"Iniciando discover | canais={canal_ids or 'todos'} | "
            f"dias={janela} | max={max_v} | dry={dry} | auto_triage={triage}"
        )
        self._set_busy(True)

        self._worker = _DiscoverWorker(
            self._service, canal_ids, janela, max_v, dry, triage, self
        )
        self._worker.finished.connect(self._on_discover_done)
        self._worker.error.connect(self._on_discover_error)
        self._worker.start()

    def _on_run_adhoc(self) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "Ocupado", "Aguarde o discover atual terminar.")
            return

        handle = self._adhoc_input.text().strip()
        if not handle:
            QMessageBox.information(self, "Campo vazio", "Informe o handle ou URL do canal.")
            return

        persist = self._chk_persist.isChecked()
        janela = self._spin_dias.value()
        max_v = self._spin_max.value()
        dry = self._chk_dry.isChecked()

        self._log_append(
            f"Discover ad-hoc | handle={handle} | persist={persist} | "
            f"dias={janela} | max={max_v} | dry={dry}"
        )
        self._set_busy(True)

        self._worker = _AdhocWorker(
            self._service, handle, persist, janela, max_v, dry, self
        )
        self._worker.finished.connect(self._on_adhoc_done)
        self._worker.error.connect(self._on_discover_error)
        self._worker.start()

    @Slot(int)
    def _on_discover_done(self, _n: int) -> None:
        self._log_append("✓ Discover concluído.")
        self._set_busy(False)
        self._refresh_videos_cb()

    @Slot(int)
    def _on_adhoc_done(self, n: int) -> None:
        self._log_append(f"✓ Discover ad-hoc concluído — {n} vídeo(s) inseridos.")
        self._set_busy(False)
        if self._chk_persist.isChecked():
            self._load_canais()
            self.canais_changed.emit()
        self._refresh_videos_cb()

    @Slot(str)
    def _on_discover_error(self, msg: str) -> None:
        self._log_append(f"✗ Erro: {msg}")
        self._set_busy(False)
        QMessageBox.critical(self, "Erro no discover", msg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        self._run_btn.setEnabled(not busy)
        self._adhoc_btn.setEnabled(not busy)
        self._run_btn.setText("Executando…" if busy else "▶  Rodar Discover")

    def _log_append(self, msg: str) -> None:
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())
