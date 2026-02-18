from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from utils.file_utils import validate_image_folder


class ImportDialog(QDialog):
    def __init__(self, dataset_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Import into {dataset_name}")
        self.resize(560, 220)
        self.selected_folder: Path | None = None

        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._pick_folder)

        row = QHBoxLayout()
        row.addWidget(self.folder_edit)
        row.addWidget(browse_btn)

        self.preview_label = QLabel("No folder selected")
        self.description_edit = QLineEdit(f"Import into {dataset_name}")
        self.replace_checkbox = QCheckBox("Replace dataset content (remove missing files)")
        self.replace_checkbox.setToolTip(
            "When enabled, files not present in the source folder will be removed from the dataset."
        )

        self.import_btn = QPushButton("Import & Publish")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self.accept)

        form = QFormLayout()
        form.addRow("Source folder", row)
        form.addRow("Preview", self.preview_label)
        form.addRow("Description", self.description_edit)
        form.addRow("", self.replace_checkbox)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addStretch()
        layout.addWidget(self.import_btn)

    def _pick_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select image folder")
        if not chosen:
            return

        folder = Path(chosen)
        ok, msg, count, size = validate_image_folder(folder)
        self.folder_edit.setText(str(folder))
        self.selected_folder = folder

        if ok:
            self.preview_label.setText(f"{count} files, {size / (1024 * 1024):.2f} MB")
            self.import_btn.setEnabled(True)
        else:
            self.preview_label.setText(msg)
            self.import_btn.setEnabled(False)

    def get_values(self) -> tuple[Path, str, bool]:
        if not self.selected_folder:
            raise RuntimeError("No folder selected")
        return (
            self.selected_folder,
            self.description_edit.text().strip(),
            self.replace_checkbox.isChecked(),
        )
