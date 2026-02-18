from __future__ import annotations

from pathlib import Path

import yaml

from core.config import (
    BROKEN_DVC_URL,
    DEFAULT_DVC_URL,
    DEFAULT_MINGIT_URL,
    LEGACY_MINGIT_URL,
    load_config,
    save_config,
)


def test_load_config_migrates_broken_dvc_url(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "workspace_root": str(tmp_path / "ws"),
                "registry_path": "registry.json",
                "locks_path": str(tmp_path / "locks"),
                "dvc_url": BROKEN_DVC_URL,
                "mingit_url": LEGACY_MINGIT_URL,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    cfg = load_config(cfg_path)

    assert cfg.dvc_url == DEFAULT_DVC_URL
    assert cfg.mingit_url == DEFAULT_MINGIT_URL
    assert cfg.registry_sources == ["registry.json"]
    reloaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert reloaded["dvc_url"] == DEFAULT_DVC_URL
    assert reloaded["mingit_url"] == DEFAULT_MINGIT_URL
    assert reloaded["registry_sources"] == ["registry.json"]


def test_save_config_updates_workspace_root(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    cfg = load_config(cfg_path)
    cfg.workspace_root = str(tmp_path / "custom-workspaces")
    cfg.registry_sources = ["alt-registry.json"]

    written_path = save_config(cfg, cfg_path)

    assert written_path == cfg_path
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert raw["workspace_root"] == cfg.workspace_root
    assert raw["registry_sources"] == [cfg.registry_path, "alt-registry.json"]
    assert Path(cfg.workspace_root).exists()
