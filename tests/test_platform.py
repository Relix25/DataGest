from __future__ import annotations

from pathlib import Path

from utils.platform import get_app_gitconfig_path, validate_unc_path


def test_validate_unc_rejects_local_path() -> None:
    assert validate_unc_path(r"C:\Data\repo", must_exist=False) is False


def test_validate_unc_rejects_invalid_unc_syntax() -> None:
    assert validate_unc_path(r"\\ServerOnly", must_exist=False) is False


def test_validate_unc_accepts_unc_syntax_without_existence_check() -> None:
    assert validate_unc_path(r"\\Server\Share\Folder\registry.json", must_exist=False) is True


def test_get_app_gitconfig_path_uses_local_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = get_app_gitconfig_path()
    assert path is not None
    assert path.name == "gitconfig"
    assert path.parent.exists()

