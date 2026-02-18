from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from utils.platform import get_local_appdata

BROKEN_DVC_URL = "https://github.com/iterative/dvc/releases/latest/download/dvc.exe"
DEFAULT_DVC_URL = "https://downloads.dvc.org/exe/dvc-3.66.1.exe"
LEGACY_MINGIT_URL = (
    "https://github.com/git-for-windows/git/releases/download/"
    "v2.53.0.windows.1/MinGit-2.53.0-busybox-64-bit.zip"
)
DEFAULT_MINGIT_URL = (
    "https://github.com/git-for-windows/git/releases/download/"
    "v2.53.0.windows.1/MinGit-2.53.0-64-bit.zip"
)


@dataclass(slots=True)
class AppConfig:
    workspace_root: str = r"C:\DataGest\workspaces"
    registry_path: str = r"\\Server\DataProjects\registry\registry.json"
    registry_sources: list[str] = field(default_factory=list)
    locks_path: str = r"\\Server\DataProjects\locks"
    log_level: str = "INFO"
    lock_ttl_hours: float = 4.0
    admin_mode: bool = False
    git_executable: str | None = None
    dvc_executable: str | None = None
    mingit_lan: str | None = None
    dvc_lan: str | None = None
    mingit_url: str = DEFAULT_MINGIT_URL
    dvc_url: str = DEFAULT_DVC_URL
    git_timeout_seconds: float = 300.0
    dvc_timeout_seconds: float = 1800.0

    @property
    def workspace_root_path(self) -> Path:
        return Path(self.workspace_root)

    @property
    def registry_path_obj(self) -> Path:
        return Path(self.registry_path)

    @property
    def locks_path_obj(self) -> Path:
        return Path(self.locks_path)


def _config_path(path: Path | None = None) -> Path:
    if path:
        return path
    base = get_local_appdata()
    base.mkdir(parents=True, exist_ok=True)
    return base / "config.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _write_yaml(path: Path, cfg: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(asdict(cfg), f, sort_keys=False)


def _normalize_registry_sources(registry_path: str, sources: list[str]) -> list[str]:
    def normalize_item(value: str) -> str:
        text = str(value).strip().strip('"')
        if not text:
            return ""

        path = Path(text)
        if path.name.lower() == "registry.json":
            return str(path)

        if path.name.lower() == "registry":
            return str(path / "registry.json")

        if path.exists() and path.is_dir():
            nested = path / "registry" / "registry.json"
            direct = path / "registry.json"
            if nested.exists():
                return str(nested)
            if direct.exists():
                return str(direct)

        normalized_text = text.replace("\\", "/").rstrip("/").lower()
        if normalized_text.endswith("/registry"):
            return str(path / "registry.json")

        return text

    normalized: list[str] = []
    seen: set[str] = set()
    for item in [registry_path, *sources]:
        text = normalize_item(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = _config_path(path)
    data = _load_yaml(cfg_path)

    cfg = AppConfig(**{k: v for k, v in data.items() if k in AppConfig.__dataclass_fields__})
    config_changed = False

    if cfg.dvc_url == BROKEN_DVC_URL:
        cfg.dvc_url = DEFAULT_DVC_URL
        config_changed = True
    if cfg.mingit_url == LEGACY_MINGIT_URL:
        cfg.mingit_url = DEFAULT_MINGIT_URL
        config_changed = True
    normalized_sources = _normalize_registry_sources(cfg.registry_path, cfg.registry_sources)
    if normalized_sources != cfg.registry_sources:
        cfg.registry_sources = normalized_sources
        config_changed = True
    if normalized_sources and cfg.registry_path != normalized_sources[0]:
        cfg.registry_path = normalized_sources[0]
        config_changed = True

    if not cfg_path.exists():
        _write_yaml(cfg_path, cfg)
    elif config_changed:
        _write_yaml(cfg_path, cfg)

    cfg.workspace_root_path.mkdir(parents=True, exist_ok=True)
    return cfg


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    cfg_path = _config_path(path)
    cfg.registry_sources = _normalize_registry_sources(cfg.registry_path, cfg.registry_sources)
    _write_yaml(cfg_path, cfg)
    cfg.workspace_root_path.mkdir(parents=True, exist_ok=True)
    return cfg_path
