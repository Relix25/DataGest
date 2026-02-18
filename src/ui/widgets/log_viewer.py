from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
)


class LogViewerDialog(QDialog):
    def __init__(self, log_file: Path, parent=None) -> None:
        super().__init__(parent)
        self.log_file = Path(log_file)
        self.setWindowTitle("Application Logs")
        self.resize(900, 500)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_logs)

        export_btn = QPushButton("Export Logs")
        export_btn.clicked.connect(self.export_logs)

        row = QHBoxLayout()
        row.addWidget(refresh_btn)
        row.addWidget(export_btn)
        row.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.editor)

        self.load_logs()

    def load_logs(self) -> None:
        if not self.log_file.exists():
            self.editor.setPlainText("No logs yet.")
            return
        self.editor.setPlainText(self.log_file.read_text(encoding="utf-8", errors="ignore"))

    def export_logs(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export logs",
            "datagest.log",
            "Log files (*.log);;All files (*.*)",
        )
        if not target:
            return

        try:
            Path(target).write_text(self.editor.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "Export", "Logs exported successfully.")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
