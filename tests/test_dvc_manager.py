from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest

from core.dvc_manager import DVCError, DVCManager


def _cp(rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["dvc"], returncode=rc, stdout=out, stderr=err)


def test_dvc_status_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dvc = DVCManager(tmp_path)
    monkeypatch.setattr(dvc, "_run", lambda args, cwd=None: _cp(out="up to date"))
    assert dvc.status() == "up to date"


def test_dvc_status_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dvc = DVCManager(tmp_path)
    monkeypatch.setattr(dvc, "_run", lambda args, cwd=None: _cp(rc=1, err="no remote"))
    with pytest.raises(DVCError):
        dvc.status()


def test_dvc_stream_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dvc = DVCManager(tmp_path)
    progress: list[int] = []

    class _FakeProc:
        def __init__(self) -> None:
            self.stdout = io.StringIO("stage 10%\nstage 90%\n")

        def wait(self, timeout=None) -> int:
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _FakeProc())
    dvc.push(progress_cb=lambda msg, p: progress.append(p))
    assert 10 in progress
    assert 90 in progress


def test_dvc_status_retries_on_readonly_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dvc = DVCManager(tmp_path)
    calls = {"count": 0}
    repaired: list[bool] = []

    def fake_run(args, cwd=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return _cp(rc=1, err="attempt to write a readonly database")
        return _cp(out="up to date")

    monkeypatch.setattr(dvc, "_run", fake_run)
    monkeypatch.setattr(dvc, "_repair_local_state_db", lambda: repaired.append(True))

    assert dvc.status() == "up to date"
    assert calls["count"] == 2
    assert repaired


def test_dvc_env_disables_analytics(tmp_path: Path) -> None:
    dvc = DVCManager(tmp_path)
    env = dvc._base_env()
    assert env["DVC_NO_ANALYTICS"] == "1"


def test_dvc_env_injects_safe_directory_for_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    dvc = DVCManager(tmp_path)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.autocrlf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")

    env = dvc._base_env()

    assert "GIT_CONFIG_GLOBAL" in env
    assert Path(env["GIT_CONFIG_GLOBAL"]).name == "gitconfig"
    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_1"] == "safe.directory"
    assert env["GIT_CONFIG_VALUE_1"] == tmp_path.resolve().as_posix()


def test_dvc_stream_terminates_process_when_callback_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dvc = DVCManager(tmp_path)
    state: dict[str, bool] = {"terminated": False, "waited": False}

    class _FakeProc:
        def __init__(self) -> None:
            self.stdout = io.StringIO("stage 10%\n")

        def wait(self, timeout=None) -> int:
            state["waited"] = True
            return 1

        def terminate(self) -> None:
            state["terminated"] = True

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _FakeProc())

    with pytest.raises(RuntimeError):
        dvc.push(progress_cb=lambda msg, p: (_ for _ in ()).throw(RuntimeError("cancel")))

    assert state["terminated"] is True
    assert state["waited"] is True


def test_dvc_status_timeout_raises_dvc_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dvc = DVCManager(tmp_path, timeout_seconds=1.0)

    def raise_timeout(args, cwd=None):
        raise subprocess.TimeoutExpired(cmd=["dvc", *args], timeout=1.0)

    monkeypatch.setattr(dvc, "_run", raise_timeout)
    with pytest.raises(DVCError, match="timed out"):
        dvc.status()


def test_dvc_stream_timeout_kills_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dvc = DVCManager(tmp_path, timeout_seconds=1.0)
    state: dict[str, bool] = {"killed": False}

    class _FakeProc:
        def __init__(self) -> None:
            self.stdout = io.StringIO("")

        def wait(self, timeout=None) -> int:
            if timeout is not None and not state["killed"]:
                raise subprocess.TimeoutExpired(cmd=["dvc", "pull"], timeout=timeout)
            return 1

        def kill(self) -> None:
            state["killed"] = True

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _FakeProc())

    with pytest.raises(DVCError, match="timed out"):
        dvc.pull()
    assert state["killed"] is True
