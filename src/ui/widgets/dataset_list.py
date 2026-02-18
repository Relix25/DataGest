from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from models.project import DatasetInfo


class DatasetListWidget(QWidget):
    dataset_selected = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._datasets: list[DatasetInfo] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search datasets...")
        self.search_input.textChanged.connect(self._apply_filter)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_row_changed)

        layout = QVBoxLayout(self)
        title = QLabel("Datasets")
        title.setProperty("role", "cardTitle")
        layout.addWidget(title)
        layout.addWidget(self.search_input)
        layout.addWidget(self.list_widget)

    def set_datasets(self, datasets: list[DatasetInfo]) -> None:
        self._datasets = datasets
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search_input.text().strip().lower()
        self.list_widget.clear()

        for ds in self._datasets:
            if (
                query
                and query not in ds.config.name.lower()
                and query not in ds.config.dataset_id.lower()
                and query not in ds.config.source.lower()
            ):
                continue

            lock_mark = " [LOCKED]" if ds.is_locked else ""
            text = f"{ds.config.name} | files: {ds.file_count}{lock_mark}"
            item = QListWidgetItem(text)
            item.setData(1, ds)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self.list_widget.item(row)
        if not item:
            return
        self.dataset_selected.emit(item.data(1))
