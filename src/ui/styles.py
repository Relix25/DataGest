APP_STYLE = """
QWidget {
    background: #1a1a2e;
    color: #ecf0f3;
    font-family: Segoe UI;
    font-size: 12px;
}

QMainWindow {
    background: #1a1a2e;
}

QListWidget, QTreeWidget, QTextEdit, QPlainTextEdit, QLineEdit, QComboBox {
    background: #16213e;
    border: 1px solid #0f3460;
    border-radius: 8px;
    padding: 6px;
}

QPushButton {
    background: #0f3460;
    border: 1px solid #1f4d80;
    border-radius: 8px;
    padding: 6px 12px;
    color: #ecf0f3;
}

QPushButton:hover {
    background: #155082;
}

QPushButton:disabled {
    background: #3a3f5b;
    color: #9097ad;
}

QLabel[role="cardTitle"] {
    font-size: 14px;
    font-weight: 600;
}

QLabel[badge="synced"] {
    background: #2d8a54;
    border-radius: 10px;
    padding: 3px 8px;
}

QLabel[badge="dirty"] {
    background: #c47f2a;
    border-radius: 10px;
    padding: 3px 8px;
}

QLabel[badge="error"] {
    background: #b64e4e;
    border-radius: 10px;
    padding: 3px 8px;
}

QLabel[badge="offline"] {
    background: #666a7d;
    border-radius: 10px;
    padding: 3px 8px;
}

QProgressBar {
    border: 1px solid #0f3460;
    border-radius: 7px;
    text-align: center;
    background: #16213e;
}

QProgressBar::chunk {
    background-color: #53bfa2;
    border-radius: 6px;
}

QTabWidget::pane {
    border: 1px solid #0f3460;
    background: #16213e;
    top: -1px;
}

QTabBar::tab {
    background: #0f3460;
    color: #ecf0f3;
    border: 1px solid #1f4d80;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 6px 12px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #16213e;
    color: #ffffff;
}

QTabBar::tab:!selected {
    color: #c9d2e0;
}
"""
