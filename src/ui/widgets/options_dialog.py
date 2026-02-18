from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class OptionsDialog(QDialog):
    def __init__(self, workspace_root: str, registry_sources: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(760, 360)

        self.workspace_edit = QLineEdit(workspace_root)
        workspace_browse_btn = QPushButton("Browse")
        workspace_browse_btn.clicked.connect(self._browse_workspace)

        workspace_row = QHBoxLayout()
        workspace_row.addWidget(self.workspace_edit)
        workspace_row.addWidget(workspace_browse_btn)

        self.registry_sources_edit = QPlainTextEdit()
        self.registry_sources_edit.setPlaceholderText(
            "One registry.json path per line (UNC or local path)"
        )
        self.registry_sources_edit.setPlainText("\n".join(registry_sources))

        add_registry_btn = QPushButton("Add Registry File")
        add_registry_btn.clicked.connect(self._add_registry_file)

        note = QLabel("Configure local workspace and available registry sources.")

        form = QFormLayout()
        form.addRow("Workspace root", workspace_row)
        form.addRow("Registry sources", self.registry_sources_edit)
        form.addRow("", add_registry_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._accept_if_valid)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(cancel_btn)
        actions.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addLayout(form)
        layout.addStretch()
        layout.addLayout(actions)

    @property
    def workspace_root(self) -> str:
        return self.workspace_edit.text().strip()

    @property
    def registry_sources(self) -> list[str]:
        seen: set[str] = set()
        values: list[str] = []
        for line in self.registry_sources_edit.toPlainText().splitlines():
            text = line.strip()
            if text and text not in seen:
                seen.add(text)
                values.append(text)
        return values

    def _browse_workspace(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select workspace root", self.workspace_root)
        if chosen:
            self.workspace_edit.setText(chosen)

    def _add_registry_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select registry.json",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not selected:
            return
        current = self.registry_sources
        if selected in current:
            return
        current.append(selected)
        self.registry_sources_edit.setPlainText("\n".join(current))

    def _accept_if_valid(self) -> None:
        value = self.workspace_root
        if not value:
            QMessageBox.warning(self, "Invalid path", "Workspace root cannot be empty.")
            return

        path = Path(value)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Invalid path", f"Cannot create workspace folder:\n{exc}")
            return

        if not self.registry_sources:
            QMessageBox.warning(self, "Invalid sources", "At least one registry source is required.")
            return

        self.accept()
