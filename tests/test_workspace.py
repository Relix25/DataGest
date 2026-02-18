from __future__ import annotations

import logging
from pathlib import Path

from core.git_manager import GitError
from core.workspace import WorkspaceManager, WorkspaceState
from models.project import DatasetConfig, ProjectConfig


class FakeGit:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self._clean = True
        self._detached = False
        self.clone_calls = 0
        self.clone_remotes: list[str] = []
        self.run_calls: list[tuple[list[str], Path | None]] = []

    def clone(self, remote: str, path: Path) -> None:
        self.clone_calls += 1
        self.clone_remotes.append(remote)
        path.mkdir(parents=True, exist_ok=True)
        (path / ".git").mkdir(exist_ok=True)

    def run(self, args, cwd=None):
        self.run_calls.append((list(args), cwd))
        if args[:2] == ["rev-parse", "--is-inside-work-tree"]:
            return "true"
        return ""

    def status(self):
        class S:
            clean = self._clean
            detached = self._detached
            branch = "main"
        return S()

    def log(self, path_filter=None, max_count=1):
        return []

    def checkout(self, ref):
        return None

    def add(self, paths):
        return None

    def commit(self, message):
        return None

    def push(self, remote="origin", branch="main"):
        return None


class FakeDVC:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.last_remote_path: str | None = None

    def init(self):
        (self.workspace / ".dvc").mkdir(exist_ok=True)

    def set_default_remote(self, remote_name, remote_path):
        self.last_remote_path = remote_path
        return None

    def status(self):
        return ""


def _project() -> ProjectConfig:
    return ProjectConfig(
        project_id="p1",
        name="P1",
        description="desc",
        git_remote="remote",
        dvc_remote="dvc",
        datasets=[DatasetConfig("d1", "D1", "desc", "src")],
    )


def test_workspace_ready_state(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)
    assert ws.init_workspace(_project())
    assert ws.get_state() == WorkspaceState.READY


def test_workspace_dirty_state(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)
    ws.init_workspace(_project())
    git._clean = False
    assert ws.get_state() == WorkspaceState.DIRTY


def test_workspace_detached_state(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)
    ws.init_workspace(_project())
    git._detached = True
    assert ws.get_state() == WorkspaceState.DETACHED


def test_workspace_recovers_when_existing_folder_is_not_git_repo(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)
    project = _project()

    bad_workspace = tmp_path / project.project_id
    bad_workspace.mkdir(parents=True, exist_ok=True)
    (bad_workspace / "orphan.txt").write_text("x", encoding="utf-8")

    assert ws.init_workspace(project) is True
    assert git.clone_calls == 1
    backups = list(tmp_path.glob("p1_corrupt_*"))
    assert backups


def test_workspace_uses_fallback_remote_sources(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)

    fallback_git = tmp_path / "share_b" / "p1.git"
    fallback_dvc = tmp_path / "share_b" / "dvc"
    fallback_git.mkdir(parents=True, exist_ok=True)
    fallback_dvc.mkdir(parents=True, exist_ok=True)

    project = ProjectConfig(
        project_id="p1",
        name="P1",
        description="desc",
        git_remote=str(tmp_path / "share_a" / "missing.git"),
        dvc_remote=str(tmp_path / "share_a" / "missing-dvc"),
        datasets=[DatasetConfig("d1", "D1", "desc", "src")],
        git_remote_sources=[str(fallback_git)],
        dvc_remote_sources=[str(fallback_dvc)],
    )

    assert ws.init_workspace(project) is True
    assert git.clone_remotes[-1] == str(fallback_git)
    assert dvc.last_remote_path == str(fallback_dvc)


def test_workspace_adds_safe_directory_on_init(tmp_path: Path) -> None:
    git = FakeGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)

    assert ws.init_workspace(_project()) is True
    expected_workspace = (tmp_path / "p1").resolve().as_posix()
    assert any(
        call[0][:4] == ["config", "--global", "--add", "safe.directory"]
        and call[0][-1] == expected_workspace
        for call in git.run_calls
    )


def test_workspace_adds_posix_safe_directory_even_with_backslash_entry(tmp_path: Path) -> None:
    class BackslashSafeGit(FakeGit):
        def __init__(self, workspace: Path) -> None:
            super().__init__(workspace)
            self.added: list[str] = []

        def run(self, args, cwd=None):
            self.run_calls.append((list(args), cwd))
            if args[:4] == ["config", "--global", "--get-all", "safe.directory"]:
                return str((tmp_path / "p1").resolve())  # backslashes on Windows
            if args[:4] == ["config", "--global", "--add", "safe.directory"]:
                self.added.append(args[-1])
                return ""
            if args[:2] == ["rev-parse", "--is-inside-work-tree"]:
                expected = (tmp_path / "p1").resolve().as_posix()
                if expected not in self.added:
                    raise GitError("fatal: detected dubious ownership in repository")
                return "true"
            return ""

    git = BackslashSafeGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)

    assert ws.init_workspace(_project()) is True
    assert (tmp_path / "p1").resolve().as_posix() in git.added


def test_workspace_init_continues_when_global_gitconfig_is_locked(tmp_path: Path) -> None:
    class LockedGlobalConfigGit(FakeGit):
        def run(self, args, cwd=None):
            self.run_calls.append((list(args), cwd))
            if args[:4] == ["config", "--global", "--get-all", "safe.directory"]:
                return ""
            if args[:4] == ["config", "--global", "--add", "safe.directory"]:
                raise GitError("error: could not lock config file C:/Users/user/.gitconfig: Permission denied")
            if args[:2] == ["rev-parse", "--is-inside-work-tree"]:
                return "true"
            return ""

    git = LockedGlobalConfigGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)

    assert ws.init_workspace(_project()) is True


def test_workspace_logs_when_dvc_status_fails(tmp_path: Path, caplog) -> None:
    class FailingDVC(FakeDVC):
        def status(self):
            raise RuntimeError("dvc status failed")

    git = FakeGit(tmp_path)
    dvc = FailingDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)
    assert ws.init_workspace(_project()) is True

    caplog.set_level(logging.WARNING)
    dirty = ws._dvc_dirty_datasets()
    assert dirty == set()
    assert "Failed to get DVC status" in caplog.text


def test_workspace_list_datasets_warns_on_missing_yaml_keys(tmp_path: Path, caplog) -> None:
    git = FakeGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)
    assert ws.init_workspace(_project()) is True

    dataset_root = ws.workspace_path / "datasets" / "d1"
    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "dataset.yaml").write_text(
        "dataset_id: d1\nname: Camera 1\n",
        encoding="utf-8",
    )

    caplog.set_level(logging.WARNING)
    datasets = ws.list_datasets()

    assert len(datasets) == 1
    assert datasets[0].config.dataset_id == "d1"
    assert datasets[0].config.name == "Camera 1"
    assert "Dataset metadata missing keys" in caplog.text


def test_workspace_list_datasets_warns_on_invalid_yaml(tmp_path: Path, caplog) -> None:
    git = FakeGit(tmp_path)
    dvc = FakeDVC(tmp_path)
    ws = WorkspaceManager(tmp_path, git, dvc)
    assert ws.init_workspace(_project()) is True

    dataset_root = ws.workspace_path / "datasets" / "d1"
    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "dataset.yaml").write_text(
        "dataset_id: d1\nname: [\n",
        encoding="utf-8",
    )

    caplog.set_level(logging.WARNING)
    datasets = ws.list_datasets()

    assert len(datasets) == 1
    assert datasets[0].config.dataset_id == "d1"
    assert datasets[0].config.name == "d1"
    assert "Invalid dataset metadata YAML" in caplog.text
