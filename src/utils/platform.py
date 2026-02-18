from __future__ import annotations

import os
import platform
from pathlib import Path
import re


def get_windows_username() -> str:
    try:
        return os.getlogin()
    except OSError:
        return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"


def get_machine_name() -> str:
    return platform.node() or "unknown-machine"


def get_local_appdata() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "DataGest"
    return Path.home() / ".datagest"


def get_app_gitconfig_path() -> Path | None:
    base = get_local_appdata()
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return base / "gitconfig"


def validate_unc_path(path: str, must_exist: bool = True) -> bool:
    if not path:
        return False
    normalized = path.strip()
    if not normalized.startswith("\\\\"):
        return False
    if not re.match(r"^\\\\[^\\\/]+\\[^\\\/]+(?:\\.*)?$", normalized):
        return False
    return Path(normalized).exists() if must_exist else True
