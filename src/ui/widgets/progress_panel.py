from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ProgressPanel(QWidget):
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()

        self.message_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)

        self.toggle_btn = QPushButton("Show Logs")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._toggle_logs)

        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setVisible(False)

        top = QHBoxLayout()
        top.addWidget(self.message_label)
        top.addStretch()
        top.addWidget(self.toggle_btn)
        top.addWidget(self.cancel_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.logs)

    def set_running(self, running: bool) -> None:
        self.cancel_btn.setEnabled(running)

    def update_progress(self, message: str, percent: int) -> None:
        self.message_label.setText(message)
        self.progress_bar.setValue(percent)
        self.append_log(f"[{percent:3d}%] {message}")

    def append_log(self, line: str) -> None:
        self.logs.appendPlainText(line)

    def set_finished(self, success: bool, message: str) -> None:
        self.message_label.setText(message)
        if success:
            self.progress_bar.setValue(100)
        self.set_running(False)

    def clear(self) -> None:
        self.logs.clear()
        self.progress_bar.setValue(0)
        self.message_label.setText("Ready")

    def _toggle_logs(self, checked: bool) -> None:
        self.logs.setVisible(checked)
        self.toggle_btn.setText("Hide Logs" if checked else "Show Logs")
