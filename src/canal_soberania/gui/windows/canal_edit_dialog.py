"""Dialog para criar/editar um canal monitorado."""

from __future__ import annotations

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from canal_soberania.config import Canal


class CanalEditDialog(QDialog):
    """Cria ou edita um Canal. Emite `canal_saved` com o objeto Canal ao confirmar."""

    canal_saved = Signal(object)  # Canal

    def __init__(self, canal: Canal | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._canal = canal
        self._setup_ui()
        if canal is not None:
            self._populate(canal)

    def _setup_ui(self) -> None:
        self.setWindowTitle("Editar canal" if self._canal else "Adicionar canal")
        self.setMinimumWidth(480)

        outer = QVBoxLayout(self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._id = QLineEdit()
        self._id.setPlaceholderText("slug_snake_case único")
        if self._canal:
            self._id.setReadOnly(True)
            self._id.setToolTip("ID não pode ser alterado após a criação")
        form.addRow("ID *", self._id)

        self._nome = QLineEdit()
        self._nome.setPlaceholderText("Nome de exibição")
        form.addRow("Nome *", self._nome)

        self._handle = QLineEdit()
        self._handle.setPlaceholderText("@handle ou vazio")
        form.addRow("Handle YouTube", self._handle)

        self._channel_url = QLineEdit()
        self._channel_url.setPlaceholderText("https://www.youtube.com/@...")
        form.addRow("URL do canal *", self._channel_url)

        self._tema = QLineEdit()
        self._tema.setPlaceholderText("ex: geopolitica_soberania")
        form.addRow("Tema primário", self._tema)

        self._peso = QDoubleSpinBox()
        self._peso.setRange(0.1, 5.0)
        self._peso.setSingleStep(0.1)
        self._peso.setValue(1.0)
        self._peso.setDecimals(1)
        form.addRow("Peso", self._peso)

        self._tolerancia = QComboBox()
        for opt in ("desconhecida", "alta", "media", "baixa"):
            self._tolerancia.addItem(opt, opt)
        form.addRow("Tolerância cortes", self._tolerancia)

        self._auto_publish = QCheckBox("Auto-publicar (sem revisão manual)")
        form.addRow("", self._auto_publish)

        self._ativo = QCheckBox("Canal ativo (incluir no discover)")
        self._ativo.setChecked(True)
        form.addRow("", self._ativo)

        self._nota = QTextEdit()
        self._nota.setMaximumHeight(72)
        self._nota.setPlaceholderText("Observações livres…")
        form.addRow("Nota", self._nota)

        outer.addLayout(form)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #b71c1c;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        outer.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _populate(self, canal: Canal) -> None:
        self._id.setText(canal.id)
        self._nome.setText(canal.nome)
        self._handle.setText(canal.handle)
        self._channel_url.setText(canal.channel_url)
        self._tema.setText(canal.tema_primario)
        self._peso.setValue(canal.peso)
        idx = self._tolerancia.findData(canal.tolerancia_cortes)
        if idx >= 0:
            self._tolerancia.setCurrentIndex(idx)
        self._auto_publish.setChecked(canal.auto_publish)
        self._ativo.setChecked(canal.ativo)
        self._nota.setPlainText(canal.nota)

    def _on_save(self) -> None:
        canal_id = self._id.text().strip()
        nome = self._nome.text().strip()
        channel_url = self._channel_url.text().strip()

        if not canal_id:
            self._show_error("ID é obrigatório.")
            return
        if not re.match(r"^[a-z0-9_]+$", canal_id):
            self._show_error("ID deve conter apenas letras minúsculas, números e _")
            return
        if not nome:
            self._show_error("Nome é obrigatório.")
            return
        if not channel_url:
            self._show_error("URL do canal é obrigatória.")
            return

        handle = self._handle.text().strip()
        if handle and not handle.startswith("@"):
            handle = f"@{handle}"

        canal = Canal(
            id=canal_id,
            nome=nome,
            handle=handle,
            channel_url=channel_url,
            tema_primario=self._tema.text().strip(),
            peso=self._peso.value(),
            tolerancia_cortes=self._tolerancia.currentData(),
            auto_publish=self._auto_publish.isChecked(),
            ativo=self._ativo.isChecked(),
            nota=self._nota.toPlainText().strip(),
        )
        self.canal_saved.emit(canal)
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
        self.adjustSize()
