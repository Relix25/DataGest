from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.git_manager import GitError, GitManager


def _cp(rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=rc, stdout=out, stderr=err)


def test_git_run_raises_on_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gm = GitManager(tmp_path)

    monkeypatch.setattr(gm, "_run", lambda args, cwd=None: _cp(rc=1, err="boom"))

    with pytest.raises(GitError):
        gm.run(["status"])


def test_git_status_parsing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gm = GitManager(tmp_path)
    status_out = "## main...origin/main\n M datasets/a/file.jpg"
    monkeypatch.setattr(gm, "run", lambda args, cwd=None: status_out)

    status = gm.status()
    assert status.branch == "main"
    assert status.clean is False
    assert status.detached is False


def test_git_log_parsing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gm = GitManager(tmp_path)
    raw = (
        "abc123\x1fab12\x1fUser\x1f2026-02-18T12:00:00+00:00\x1fImport\x1e\n"
        "datasets/camera_1/data/img1.jpg\n"
        "datasets/camera_1/data/img2.jpg\n"
    )
    monkeypatch.setattr(gm, "run", lambda args, cwd=None: raw)

    commits = gm.log(path_filter="datasets/camera_1")
    assert len(commits) == 1
    assert commits[0].hash == "abc123"
    assert commits[0].files_changed == 2


def test_normalize_remote_url_for_local_windows_path(tmp_path: Path) -> None:
    gm = GitManager(tmp_path)
    normalized = gm._normalize_remote_url(r"C:\repo\project.git")
    assert normalized.startswith("file:///")


def test_git_run_uses_app_global_gitconfig(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gm = GitManager(tmp_path)
    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs["env"]
        return _cp()

    monkeypatch.setattr(subprocess, "run", fake_run)
    gm._run(["status"])

    assert "GIT_CONFIG_GLOBAL" in captured["env"]
    assert Path(captured["env"]["GIT_CONFIG_GLOBAL"]).name == "gitconfig"


def test_git_run_timeout_raises_giterror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gm = GitManager(tmp_path, timeout_seconds=1.0)

    def raise_timeout(args, cwd=None):
        raise subprocess.TimeoutExpired(cmd=["git", *args], timeout=1.0)

    monkeypatch.setattr(gm, "_run", raise_timeout)
    with pytest.raises(GitError, match="timed out"):
        gm.run(["status"])


def test_git_run_overrides_existing_global_config_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gm = GitManager(tmp_path)
    captured: dict = {}
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", r"C:\Users\someone\.gitconfig")

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs["env"]
        return _cp()

    monkeypatch.setattr(subprocess, "run", fake_run)
    gm._run(["status"])

    assert "GIT_CONFIG_GLOBAL" in captured["env"]
    assert Path(captured["env"]["GIT_CONFIG_GLOBAL"]).name == "gitconfig"
    assert captured["env"]["GIT_CONFIG_GLOBAL"] != r"C:\Users\someone\.gitconfig"


def test_git_run_injects_safe_directory_for_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gm = GitManager(tmp_path)
    (tmp_path / ".git").mkdir()
    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured["cmd"] = args[0]
        return _cp()

    monkeypatch.setattr(subprocess, "run", fake_run)
    gm._run(["status"])

    cmd = captured["cmd"]
    assert "-c" in cmd
    idx = cmd.index("-c")
    assert cmd[idx + 1] == f"safe.directory={tmp_path.resolve().as_posix()}"
