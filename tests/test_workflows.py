from __future__ import annotations

from pathlib import Path

from core.git_manager import GitError
from core.lock_manager import LockManager
from workflows.import_workflow import ImportWorkflow


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.git_add_args: list[list[str]] = []


class DummyGit:
    def __init__(self, rec: Recorder) -> None:
        self.rec = rec

    def pull(self, rebase=True):
        self.rec.calls.append("git.pull")

    def add(self, paths):
        self.rec.calls.append("git.add")
        self.rec.git_add_args.append(list(paths))

    def commit(self, msg):
        self.rec.calls.append("git.commit")

    def push(self, remote="origin", branch="main"):
        self.rec.calls.append("git.push")


class DummyDVC:
    def __init__(self, rec: Recorder) -> None:
        self.rec = rec

    def pull(self, progress_cb=None):
        self.rec.calls.append("dvc.pull")

    def add(self, paths, progress_cb=None):
        self.rec.calls.append("dvc.add")

    def push(self, progress_cb=None):
        self.rec.calls.append("dvc.push")


class DummyWorkspace:
    def __init__(self, root: Path, rec: Recorder) -> None:
        self.root = root
        self.rec = rec
        self.git = DummyGit(rec)
        self.dvc = DummyDVC(rec)

    def init_workspace(self, project):
        self.rec.calls.append("workspace.init")
        p = self.root / project.project_id
        (p / ".git").mkdir(parents=True, exist_ok=True)
        (p / ".dvc").mkdir(parents=True, exist_ok=True)
        return True

    def get_dataset_path(self, dataset_id: str) -> Path:
        return self.root / "p1" / "datasets" / dataset_id


def test_import_workflow_lock_fail_fast(tmp_path: Path, project_factory) -> None:
    rec = Recorder()
    workspace = DummyWorkspace(tmp_path, rec)
    lock = LockManager(tmp_path / "locks")

    project = project_factory(dataset_id="d1", dataset_name="D1")
    dataset = project.datasets[0]

    source = tmp_path / "src"
    source.mkdir()
    (source / "a.jpg").write_bytes(b"x")

    assert lock.acquire("p1", "d1") is True

    wf = ImportWorkflow(project, dataset, source, workspace, lock)

    finished: list[tuple[bool, str]] = []
    wf.finished.connect(lambda s, m: finished.append((s, m)))

    wf.execute()

    assert finished
    assert finished[-1][0] is False
    assert "locked" in finished[-1][1].lower()


def test_import_workflow_sequence(tmp_path: Path, project_factory) -> None:
    rec = Recorder()
    workspace = DummyWorkspace(tmp_path, rec)
    lock = LockManager(tmp_path / "locks")

    project = project_factory(dataset_id="d1", dataset_name="D1")
    dataset = project.datasets[0]

    source = tmp_path / "src"
    source.mkdir()
    (source / "a.jpg").write_bytes(b"x")

    wf = ImportWorkflow(project, dataset, source, workspace, lock)

    finished: list[tuple[bool, str]] = []
    wf.finished.connect(lambda s, m: finished.append((s, m)))

    wf.execute()

    assert finished[-1][0] is True
    assert rec.calls[:4] == ["workspace.init", "git.pull", "dvc.pull", "dvc.add"]
    assert "git.commit" in rec.calls
    assert rec.calls[-1] == "git.push"
    assert rec.git_add_args
    assert ".gitignore" not in rec.git_add_args[0]


def test_import_workflow_replace_mode_removes_stale_files(tmp_path: Path, project_factory) -> None:
    rec = Recorder()
    workspace = DummyWorkspace(tmp_path, rec)
    lock = LockManager(tmp_path / "locks")

    project = project_factory(dataset_id="d1", dataset_name="D1")
    dataset = project.datasets[0]

    source = tmp_path / "src"
    source.mkdir()
    (source / "new.jpg").write_bytes(b"new")

    data_dir = workspace.get_dataset_path(dataset.dataset_id) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    stale = data_dir / "stale.jpg"
    stale.write_bytes(b"old")

    wf = ImportWorkflow(project, dataset, source, workspace, lock, replace_dataset=True)
    finished: list[tuple[bool, str]] = []
    wf.finished.connect(lambda s, m: finished.append((s, m)))

    wf.execute()

    assert finished[-1][0] is True
    assert not stale.exists()
    assert (data_dir / "new.jpg").exists()
    assert "replaced dataset" in finished[-1][1].lower()


def test_import_workflow_no_changes_is_success(tmp_path: Path, project_factory) -> None:
    rec = Recorder()
    workspace = DummyWorkspace(tmp_path, rec)
    lock = LockManager(tmp_path / "locks")

    project = project_factory(dataset_id="d1", dataset_name="D1")
    dataset = project.datasets[0]

    source = tmp_path / "src"
    source.mkdir()
    (source / "a.jpg").write_bytes(b"x")

    def commit_no_change(msg: str) -> None:
        rec.calls.append("git.commit")
        raise GitError("nothing to commit, working tree clean")

    workspace.git.commit = commit_no_change  # type: ignore[method-assign]

    wf = ImportWorkflow(project, dataset, source, workspace, lock)
    finished: list[tuple[bool, str]] = []
    wf.finished.connect(lambda s, m: finished.append((s, m)))

    wf.execute()

    assert finished[-1][0] is True
    assert "up to date" in finished[-1][1].lower()
    assert "git.push" not in rec.calls


def test_import_workflow_cancelled_before_start(tmp_path: Path, project_factory) -> None:
    rec = Recorder()
    workspace = DummyWorkspace(tmp_path, rec)
    lock = LockManager(tmp_path / "locks")

    project = project_factory(dataset_id="d1", dataset_name="D1")
    dataset = project.datasets[0]

    source = tmp_path / "src"
    source.mkdir()
    (source / "a.jpg").write_bytes(b"x")

    wf = ImportWorkflow(project, dataset, source, workspace, lock)
    wf.cancel()

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    wf.finished.connect(lambda s, m: finished.append((s, m)))
    wf.error.connect(lambda msg: errors.append(msg))

    wf.execute()

    assert finished[-1][0] is False
    assert "cancelled by user" in finished[-1][1].lower()
    assert errors == []
    assert rec.calls == []
