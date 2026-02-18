from __future__ import annotations

from datetime import datetime, timezone

from models.project import CommitInfo
from workflows.history_workflow import LoadHistoryWorkflow, ReturnToLatestWorkflow, RestoreVersionWorkflow


class FakeGit:
    def __init__(self) -> None:
        self.commits = [
            CommitInfo(
                hash="c2",
                short_hash="c2",
                author="User",
                date=datetime.now(timezone.utc),
                message="Update",
                files_changed=1,
            ),
            CommitInfo(
                hash="c1",
                short_hash="c1",
                author="User",
                date=datetime.now(timezone.utc),
                message="Init",
                files_changed=1,
            ),
        ]

    def log(self, path_filter=None, max_count=50):
        return list(self.commits)

    def run(self, args, cwd=None):
        if args[:3] == ["rev-list", "--parents", "-n"]:
            commit = args[-1]
            if commit == "c2":
                return "c2 c1"
            return "c1"

        if args and args[0] == "show":
            ref = args[1]
            if ref.startswith("c2:"):
                return "outs:\n  - path: datasets/d1/data\n    nfiles: 12\n"
            if ref.startswith("c1:"):
                return "outs:\n  - path: datasets/d1/data\n    nfiles: 10\n"
            return ""
        return ""


class FakeWorkspace:
    def __init__(self) -> None:
        self.git = FakeGit()

    def init_workspace(self, project):
        return True


class RestoreFetchGit:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def checkout(self, ref: str) -> None:
        self.calls.append(f"git.checkout:{ref}")

    def pull(self, rebase: bool = True) -> None:
        self.calls.append("git.pull")


class RestoreFetchDVC:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def pull(self, progress_cb=None) -> None:
        self.calls.append("dvc.pull")

    def checkout(self, progress_cb=None) -> None:
        self.calls.append("dvc.checkout")


class RestoreFetchWorkspace:
    def __init__(self) -> None:
        self.init_calls = 0
        self.git = RestoreFetchGit()
        self.dvc = RestoreFetchDVC()

    def init_workspace(self, project) -> bool:
        self.init_calls += 1
        return True


def test_history_workflow_computes_image_deltas(project_factory) -> None:
    project = project_factory(dataset_id="d1", dataset_name="D1")
    wf = LoadHistoryWorkflow(project, "d1", FakeWorkspace())  # type: ignore[arg-type]

    finished: list[tuple[bool, str]] = []
    wf.finished.connect(lambda s, m: finished.append((s, m)))

    wf.execute()

    assert finished[-1][0] is True
    assert wf.commits[0].images_added == 2
    assert wf.commits[0].images_removed == 0
    assert wf.commits[1].images_added == 10
    assert wf.commits[1].images_removed == 0


def test_restore_workflow_cancelled_before_start(project_factory) -> None:
    project = project_factory(dataset_id="d1", dataset_name="D1")
    workspace = RestoreFetchWorkspace()
    workflow = RestoreVersionWorkflow(project, "abc123", workspace)  # type: ignore[arg-type]
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


def test_return_to_latest_workflow_cancelled_before_start(project_factory) -> None:
    project = project_factory(dataset_id="d1", dataset_name="D1")
    workspace = RestoreFetchWorkspace()
    workflow = ReturnToLatestWorkflow(project, workspace)  # type: ignore[arg-type]
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


def test_restore_workflow_success_sequence(project_factory) -> None:
    project = project_factory(dataset_id="d1", dataset_name="D1")
    workspace = RestoreFetchWorkspace()
    workflow = RestoreVersionWorkflow(project, "abc123", workspace)  # type: ignore[arg-type]

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))
    workflow.error.connect(lambda msg: errors.append(msg))

    workflow.execute()

    assert finished[-1][0] is True
    assert errors == []
    assert workspace.init_calls == 1
    assert workspace.git.calls == ["git.checkout:abc123"]
    assert workspace.dvc.calls == ["dvc.checkout"]


def test_restore_workflow_fails_on_checkout_error(project_factory) -> None:
    class FailingGit(RestoreFetchGit):
        def checkout(self, ref: str) -> None:
            raise RuntimeError("checkout failed")

    class FailingWorkspace(RestoreFetchWorkspace):
        def __init__(self) -> None:
            super().__init__()
            self.git = FailingGit()

    project = project_factory(dataset_id="d1", dataset_name="D1")
    workspace = FailingWorkspace()
    workflow = RestoreVersionWorkflow(project, "abc123", workspace)  # type: ignore[arg-type]

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))
    workflow.error.connect(lambda msg: errors.append(msg))

    workflow.execute()

    assert finished[-1][0] is False
    assert "checkout failed" in finished[-1][1].lower()
    assert errors


def test_return_to_latest_workflow_success_sequence(project_factory) -> None:
    project = project_factory(dataset_id="d1", dataset_name="D1")
    workspace = RestoreFetchWorkspace()
    workflow = ReturnToLatestWorkflow(project, workspace)  # type: ignore[arg-type]

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))
    workflow.error.connect(lambda msg: errors.append(msg))

    workflow.execute()

    assert finished[-1][0] is True
    assert errors == []
    assert workspace.init_calls == 1
    assert workspace.git.calls == ["git.checkout:main", "git.pull"]
    assert workspace.dvc.calls == ["dvc.pull", "dvc.checkout"]


def test_return_to_latest_workflow_fails_on_dvc_pull_error(project_factory) -> None:
    class FailingDVC(RestoreFetchDVC):
        def pull(self, progress_cb=None) -> None:
            raise RuntimeError("dvc pull failed")

    class FailingWorkspace(RestoreFetchWorkspace):
        def __init__(self) -> None:
            super().__init__()
            self.dvc = FailingDVC()

    project = project_factory(dataset_id="d1", dataset_name="D1")
    workspace = FailingWorkspace()
    workflow = ReturnToLatestWorkflow(project, workspace)  # type: ignore[arg-type]

    finished: list[tuple[bool, str]] = []
    errors: list[str] = []
    workflow.finished.connect(lambda s, m: finished.append((s, m)))
    workflow.error.connect(lambda msg: errors.append(msg))

    workflow.execute()

    assert finished[-1][0] is False
    assert "dvc pull failed" in finished[-1][1].lower()
    assert errors
