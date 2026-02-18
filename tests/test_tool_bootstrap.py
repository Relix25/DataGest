from __future__ import annotations

from pathlib import Path

from core.config import AppConfig
from core.tool_bootstrap import ToolBootstrap


def test_resolve_dvc_source_keeps_preferred_when_available(tmp_path: Path, monkeypatch) -> None:
    bootstrap = ToolBootstrap(AppConfig(), tools_dir=tmp_path)
    monkeypatch.setattr(bootstrap, "_url_exists", lambda url: url == "https://preferred")

    source = bootstrap._resolve_dvc_source("https://preferred")
    assert source == "https://preferred"


def test_resolve_dvc_source_falls_back_to_latest_version(tmp_path: Path, monkeypatch) -> None:
    bootstrap = ToolBootstrap(AppConfig(), tools_dir=tmp_path)

    def fake_url_exists(url: str) -> bool:
        return url.endswith("dvc-9.9.9.exe")

    monkeypatch.setattr(bootstrap, "_url_exists", fake_url_exists)
    monkeypatch.setattr(bootstrap, "_fetch_latest_dvc_version", lambda: "9.9.9")

    source = bootstrap._resolve_dvc_source("https://broken")
    assert source.endswith("dvc-9.9.9.exe")
