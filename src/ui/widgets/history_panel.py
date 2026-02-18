from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.project import CommitInfo


class HistoryPanel(QWidget):
    restore_requested = Signal(str)
    latest_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._commits: list[CommitInfo] = []

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)

        self.restore_btn = QPushButton("Restore Selected")
        self.latest_btn = QPushButton("Return to Latest")

        self.restore_btn.clicked.connect(self._restore_selected)
        self.latest_btn.clicked.connect(self.latest_requested.emit)

        title = QLabel("Dataset History")
        title.setProperty("role", "cardTitle")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.restore_btn)
        btn_row.addWidget(self.latest_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.tree)
        layout.addLayout(btn_row)

    def set_commits(self, commits: list[CommitInfo]) -> None:
        self._commits = commits
        self.tree.clear()

        for commit in commits:
            date_str = commit.date.strftime("%Y-%m-%d %H:%M")
            summary = (
                f"{commit.short_hash} | {date_str} | {commit.author} | "
                f"{commit.message} | images +{commit.images_added}/-{commit.images_removed}"
            )
            root = QTreeWidgetItem([summary])
            root.setData(0, Qt.UserRole, commit.hash)

            details = [
                f"Hash: {commit.hash}",
                f"Author: {commit.author}",
                f"Date: {date_str}",
                f"Files changed: {commit.files_changed}",
                f"Images added: +{commit.images_added}",
                f"Images removed: -{commit.images_removed}",
            ]
            for line in details:
                root.addChild(QTreeWidgetItem([line]))

            self.tree.addTopLevelItem(root)

        if self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _restore_selected(self) -> None:
        item = self.tree.currentItem()
        if not item:
            return
        while item.parent() is not None:
            item = item.parent()
        commit_hash = item.data(0, Qt.UserRole)
        if commit_hash:
            self.restore_requested.emit(str(commit_hash))
