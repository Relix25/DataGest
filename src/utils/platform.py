from __future__ import annotations

import getpass
import os
from pathlib import Path
import re
import socket


def get_windows_username() -> str:
    try:
        username = getpass.getuser()
        return username or "unknown"
    except Exception:
        return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"


def get_machine_name() -> str:
    try:
        name = socket.gethostname()
        return name or "unknown-machine"
    except Exception:
        return "unknown-machine"


def get_local_appdata() -> Path:
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "DataGest"
        return Path.home() / "AppData" / "Local" / "DataGest"

    xdg_root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_root) if xdg_root else Path.home() / ".config"
    return base / "datagest"


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
