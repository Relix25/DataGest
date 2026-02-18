from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.project import DatasetInfo


class DatasetDetailWidget(QWidget):
    import_requested = Signal()
    publish_requested = Signal()
    fetch_requested = Signal()
    restore_latest_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.current_dataset: DatasetInfo | None = None
        self.current_path: Path | None = None

        self.name_label = QLabel("Select a dataset")
        self.name_label.setProperty("role", "cardTitle")
        self.state_badge = QLabel("offline")
        self.state_badge.setProperty("badge", "offline")

        self.files_label = QLabel("Files: -")
        self.size_label = QLabel("Size: -")
        self.updated_label = QLabel("Last updated: -")
        self.author_label = QLabel("Last author: -")

        self.import_btn = QPushButton("Import Folder")
        self.publish_btn = QPushButton("Commit && Push")
        self.fetch_btn = QPushButton("Pull Latest")
        self.latest_btn = QPushButton("Return to Latest")
        self.open_btn = QPushButton("Open Folder")

        self.import_btn.clicked.connect(self.import_requested.emit)
        self.publish_btn.clicked.connect(self.publish_requested.emit)
        self.fetch_btn.clicked.connect(self.fetch_requested.emit)
        self.latest_btn.clicked.connect(self.restore_latest_requested.emit)
        self.open_btn.clicked.connect(self._open_folder)

        header = QHBoxLayout()
        header.addWidget(self.name_label)
        header.addStretch()
        header.addWidget(self.state_badge)

        grid = QGridLayout()
        grid.addWidget(self.files_label, 0, 0)
        grid.addWidget(self.size_label, 0, 1)
        grid.addWidget(self.updated_label, 1, 0)
        grid.addWidget(self.author_label, 1, 1)

        btn_row = QHBoxLayout()
        for btn in [
            self.import_btn,
            self.publish_btn,
            self.fetch_btn,
            self.latest_btn,
            self.open_btn,
        ]:
            btn_row.addWidget(btn)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addLayout(grid)
        layout.addLayout(btn_row)
        layout.addStretch()

    def set_dataset(self, dataset: DatasetInfo, dataset_path: Path) -> None:
        self.current_dataset = dataset
        self.current_path = dataset_path

        self.name_label.setText(dataset.config.name)
        self.files_label.setText(f"Files: {dataset.file_count}")
        self.size_label.setText(f"Size: {dataset.total_size_bytes / (1024 * 1024):.1f} MB")

        updated = dataset.last_updated.isoformat(sep=" ", timespec="seconds") if dataset.last_updated else "-"
        self.updated_label.setText(f"Last updated: {updated}")
        self.author_label.setText(f"Last author: {dataset.last_author or '-'}")

        badge = "synced"
        if dataset.local_state in {"modified", "dirty"}:
            badge = "dirty"
        elif dataset.local_state == "not_downloaded":
            badge = "offline"

        self.state_badge.setProperty("badge", badge)
        self.state_badge.setText(dataset.local_state)
        self.style().unpolish(self.state_badge)
        self.style().polish(self.state_badge)

    def _open_folder(self) -> None:
        if self.current_path and self.current_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_path)))
