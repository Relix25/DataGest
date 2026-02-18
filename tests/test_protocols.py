from __future__ import annotations

from pathlib import Path

from core.dvc_manager import DVCManager
from core.git_manager import GitManager
from core.protocols import DVCClient, GitClient


def test_git_manager_implements_git_protocol(tmp_path: Path) -> None:
    manager = GitManager(tmp_path)
    assert isinstance(manager, GitClient)


def test_dvc_manager_implements_dvc_protocol(tmp_path: Path) -> None:
    manager = DVCManager(tmp_path)
    assert isinstance(manager, DVCClient)

