from __future__ import annotations

from core.git_manager import GitError
from models.project import ProjectConfig
from workflows.sync_workflow import FetchLatestWorkflow, PublishWorkflow


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.git_add_args: list[list[str]] = []
        self.dvc_add_args: list[list[str]] = []


class DummyGit:
    def __init__(self, rec: Recorder) -> None:
        self.rec = rec
        self.branch: str | None = "main"
        self.raise_nothing_to_commit = False

    def current_branch(self) -> str | None:
        self.rec.calls.append("git.current_branch")
        return self.branch

    def checkout(self, ref: str) -> None:
        self.rec.calls.append("git.checkout")
        self.branch = ref

    def add(self, paths: list[str]) -> None:
        self.rec.calls.append("git.add")
        self.rec.git_add_args.append(list(paths))

    def commit(self, message: str) -> None:
        self.rec.calls.append("git.commit")
        if self.raise_nothing_to_commit:
            raise GitError("nothing to commit, working tree clean")

    def pull(self, rebase: bool = True) -> None:
        self.rec.calls.append("git.pull")

    def push(self, remote: str = "origin", branch: str = "main") -> None:
        self.rec.calls.append("git.push")


class DummyDVC:
    def __init__(self, rec: Recorder) -> None:
        self.rec = rec

    def add(self, paths: list[str], progress_cb=None) -> None:
        self.rec.calls.append("dvc.add")
        self.rec.dvc_add_args.append(list(paths))

    def push(self, progress_cb=None) -> None:
        self.rec.calls.append("dvc.push")


class DummyWorkspace:
    def __init__(self, rec: Recorder) -> None:
        self.rec = rec
        self.git = DummyGit(rec)
        self.dvc = DummyDVC(rec)

    def init_workspace(self, project: ProjectConfig) -> bool:
        self.rec.calls.append("workspace.init")
        return True


class FetchGit:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def status(self):
        class S:
            clean = True
            detached = False
            branch = "main"

        self.calls.append("git.status")
        return S()

    def pull(self, rebase: bool = True) -> None:
        self.calls.append("git.pull")

    def current_branch(self) -> str | None:
        self.calls.append("git.current_branch")
        return "main"


class FetchDVC:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def pull(self, progress_cb=None) -> None:
        self.calls.append("dvc.pull")

    def checkout(self, progress_cb=None) -> None:
        self.calls.append("dvc.checkout")


class FetchWorkspace:
    def __init__(self) -> None:
        self.init_calls = 0
        self.git = FetchGit()
        self.dvc = FetchDVC()

    def init_workspace(self, project: ProjectConfig) -> bool:
        self.init_calls += 1
        return True


def test_publish_workflow_dataset_mode_stages_deletes_and_pushes(project_factory) -> None:
    rec = Recorder()
    workspace = DummyWorkspace(rec)
    project = project_factory(dataset_id="camera_1", dataset_name="Camera 1")

    workflow = PublishWorkflow(
        project=project,
        workspace=workspace,  # type: ignore[arg-type]
        commit_message="Update dataset",
        dataset_id="camera_1",
    )
    finished: list[tuple[bool, str]] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))

    workflow.execute()

    assert finished[-1][0] is True
    assert rec.dvc_add_args == [["datasets/camera_1/data"]]
    assert rec.git_add_args == [["-A", "datasets/camera_1"]]
    assert "git.pull" in rec.calls
    assert rec.calls[-1] == "git.push"


def test_publish_workflow_no_changes_is_success(project_factory) -> None:
    rec = Recorder()
    workspace = DummyWorkspace(rec)
    workspace.git.raise_nothing_to_commit = True
    project = project_factory(dataset_id="camera_1", dataset_name="Camera 1")

    workflow = PublishWorkflow(
        project=project,
        workspace=workspace,  # type: ignore[arg-type]
        commit_message="No-op",
        dataset_id="camera_1",
    )
    finished: list[tuple[bool, str]] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))

    workflow.execute()

    assert finished[-1][0] is True
    assert "no local change" in finished[-1][1].lower()
    assert "dvc.push" not in rec.calls
    assert "git.push" not in rec.calls


def test_publish_workflow_fails_on_detached_head(project_factory) -> None:
    rec = Recorder()
    workspace = DummyWorkspace(rec)
    workspace.git.branch = None
    project = project_factory(dataset_id="camera_1", dataset_name="Camera 1")

    workflow = PublishWorkflow(
        project=project,
        workspace=workspace,  # type: ignore[arg-type]
        commit_message="Update",
        dataset_id="camera_1",
    )
    finished: list[tuple[bool, str]] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))

    workflow.execute()

    assert finished[-1][0] is False
    assert "detached head" in finished[-1][1].lower()


def test_fetch_latest_workflow_cancelled_before_start(project_factory) -> None:
    project = project_factory(dataset_id="camera_1", dataset_name="Camera 1")
    workspace = FetchWorkspace()
    workflow = FetchLatestWorkflow(project=project, workspace=workspace)  # type: ignore[arg-type]
    workflow.cancel()

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))
    workflow.error.connect(lambda msg: errors.append(msg))

    workflow.execute()

    assert finished[-1][0] is False
    assert "cancelled by user" in finished[-1][1].lower()
    assert errors == []
    assert workspace.init_calls == 0


def test_fetch_latest_retries_transient_network_error(monkeypatch, project_factory) -> None:
    class RetryFetchGit(FetchGit):
        def __init__(self) -> None:
            super().__init__()
            self.pull_attempts = 0

        def pull(self, rebase: bool = True) -> None:
            self.pull_attempts += 1
            self.calls.append("git.pull")
            if self.pull_attempts == 1:
                raise RuntimeError("network path was not found")

    class RetryWorkspace(FetchWorkspace):
        def __init__(self) -> None:
            super().__init__()
            self.git = RetryFetchGit()

    monkeypatch.setattr("workflows.base.time.sleep", lambda _: None)

    project = project_factory(dataset_id="camera_1", dataset_name="Camera 1")
    workspace = RetryWorkspace()
    workflow = FetchLatestWorkflow(project=project, workspace=workspace)  # type: ignore[arg-type]

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))
    workflow.error.connect(lambda msg: errors.append(msg))

    workflow.execute()

    assert finished[-1][0] is True
    assert errors == []
    assert workspace.git.pull_attempts == 2


def test_fetch_latest_workflow_success_sequence(project_factory) -> None:
    project = project_factory(dataset_id="camera_1", dataset_name="Camera 1")
    workspace = FetchWorkspace()
    workflow = FetchLatestWorkflow(project=project, workspace=workspace)  # type: ignore[arg-type]

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))
    workflow.error.connect(lambda msg: errors.append(msg))

    workflow.execute()

    assert finished[-1][0] is True
    assert errors == []
    assert workspace.init_calls == 1
    assert workspace.git.calls == ["git.status", "git.pull", "git.current_branch"]
    assert workspace.dvc.calls == ["dvc.pull", "dvc.checkout"]


def test_fetch_latest_workflow_fails_when_workspace_dirty(project_factory) -> None:
    class DirtyFetchGit(FetchGit):
        def status(self):
            class S:
                clean = False
                detached = False
                branch = "main"

            self.calls.append("git.status")
            return S()

    class DirtyWorkspace(FetchWorkspace):
        def __init__(self) -> None:
            super().__init__()
            self.git = DirtyFetchGit()

    project = project_factory(dataset_id="camera_1", dataset_name="Camera 1")
    workspace = DirtyWorkspace()
    workflow = FetchLatestWorkflow(project=project, workspace=workspace)  # type: ignore[arg-type]

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))
    workflow.error.connect(lambda msg: errors.append(msg))

    workflow.execute()

    assert finished[-1][0] is False
    assert "local changes" in finished[-1][1].lower()
    assert errors


def test_fetch_latest_workflow_allows_dirty_when_requested(project_factory) -> None:
    class DirtyFetchGit(FetchGit):
        def status(self):
            class S:
                clean = False
                detached = False
                branch = "main"

            self.calls.append("git.status")
            return S()

    class DirtyWorkspace(FetchWorkspace):
        def __init__(self) -> None:
            super().__init__()
            self.git = DirtyFetchGit()

    project = project_factory(dataset_id="camera_1", dataset_name="Camera 1")
    workspace = DirtyWorkspace()
    workflow = FetchLatestWorkflow(
        project=project,
        workspace=workspace,  # type: ignore[arg-type]
        allow_dirty=True,
    )

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))
    workflow.error.connect(lambda msg: errors.append(msg))

    workflow.execute()

    assert finished[-1][0] is True
    assert errors == []
