from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .platform import get_local_appdata


def setup_logging(level: str = "INFO") -> Path:
    """Configure rotating file logging and return log file path."""
    base = get_local_appdata() / "logs"
    base.mkdir(parents=True, exist_ok=True)
    log_file = base / "app.log"

    root = logging.getLogger()
    root.setLevel(level.upper())

    if not root.handlers:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    return log_file
