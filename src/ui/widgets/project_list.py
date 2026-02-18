from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from models.project import ProjectConfig


class ProjectListWidget(QWidget):
    project_selected = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._projects: list[ProjectConfig] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search projects...")
        self.search_input.textChanged.connect(self._apply_filter)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_row_changed)

        layout = QVBoxLayout(self)
        title = QLabel("Projects")
        title.setProperty("role", "cardTitle")
        layout.addWidget(title)
        layout.addWidget(self.search_input)
        layout.addWidget(self.list_widget)

    def set_projects(self, projects: list[ProjectConfig]) -> None:
        self._projects = projects
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search_input.text().strip().lower()
        self.list_widget.clear()

        for project in self._projects:
            if query and query not in project.name.lower() and query not in project.project_id.lower():
                continue
            item = QListWidgetItem(f"{project.name} ({project.project_id})")
            item.setData(1, project)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self.list_widget.item(row)
        if not item:
            return
        project = item.data(1)
        self.project_selected.emit(project)

