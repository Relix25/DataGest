from __future__ import annotations

from core.git_manager import GitError
from core.workspace import WorkspaceManager
from models.project import ProjectConfig
from workflows.base import BaseWorkflow, WorkflowCancelled


class FetchLatestWorkflow(BaseWorkflow):
    def __init__(self, project: ProjectConfig, workspace: WorkspaceManager, allow_dirty: bool = False) -> None:
        super().__init__()
        self.project = project
        self.workspace = workspace
        self.allow_dirty = allow_dirty

    def execute(self) -> None:
        try:
            self._emit_progress("Preparing workspace", 5)
            self.workspace.init_workspace(self.project)
            self._check_cancelled()

            status = self.workspace.git.status()
            if not status.clean and not self.allow_dirty:
                raise RuntimeError(
                    "Workspace has local changes. Commit or discard them before fetching latest."
                )

            self._emit_progress("Pulling latest Git commits", 30)
            self._run_network_op_with_retry(
                lambda: self.workspace.git.pull(rebase=True),
                "Git pull",
            )
            self._check_cancelled()

            self._emit_progress("Pulling latest DVC objects", 55)
            self._run_network_op_with_retry(
                lambda: self.workspace.dvc.pull(progress_cb=self._emit_progress),
                "DVC pull",
            )
            self._check_cancelled()

            self._emit_progress("Checking out data", 80)
            self.workspace.dvc.checkout(progress_cb=self._emit_progress)

            branch = self.workspace.git.current_branch() or "detached"
            self._emit_progress("Fetch complete", 100)
            self._emit_finished(True, f"Workspace synced on {branch}.")
        except WorkflowCancelled as exc:
            self._emit_finished(False, str(exc))
        except Exception as exc:
            self._emit_error(str(exc))
            self._emit_finished(False, str(exc))


class PublishWorkflow(BaseWorkflow):
    def __init__(
        self,
        project: ProjectConfig,
        workspace: WorkspaceManager,
        commit_message: str,
        dataset_id: str | None = None,
        paths_to_add: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.project = project
        self.workspace = workspace
        self.commit_message = commit_message
        self.dataset_id = dataset_id
        self.paths_to_add = paths_to_add or ["."]

    def _is_non_fast_forward_error(self, message: str) -> bool:
        lowered = message.lower()
        return "non-fast-forward" in lowered or "failed to push some refs" in lowered

    def execute(self) -> None:
        try:
            self._emit_progress("Preparing workspace", 5)
            self.workspace.init_workspace(self.project)
            self._check_cancelled()

            current_branch = self.workspace.git.current_branch()
            if current_branch is None:
                raise RuntimeError(
                    "Workspace is on a restored commit (detached HEAD). Return to latest before publishing."
                )

            if current_branch != "main":
                self._emit_progress("Switching to main", 10)
                self.workspace.git.checkout("main")
                self._check_cancelled()

            paths_to_add = self.paths_to_add
            if self.dataset_id:
                rel_data = f"datasets/{self.dataset_id}/data"
                rel_dataset = f"datasets/{self.dataset_id}"
                self._emit_progress("Tracking dataset changes with DVC", 18)
                self.workspace.dvc.add([rel_data], progress_cb=self._emit_progress)
                paths_to_add = ["-A", rel_dataset]

            self._emit_progress("Staging files", 30)
            self.workspace.git.add(paths_to_add)
            self._check_cancelled()

            self._emit_progress("Creating commit", 45)
            has_changes = True
            try:
                self.workspace.git.commit(self.commit_message)
            except GitError as exc:
                if "nothing to commit" in str(exc).lower():
                    has_changes = False
                else:
                    raise

            if not has_changes:
                self._emit_progress("No changes to publish", 100)
                self._emit_finished(True, "No local change detected.")
                return

            self._emit_progress("Rebasing on latest main", 62)
            self._run_network_op_with_retry(
                lambda: self.workspace.git.pull(rebase=True),
                "Git pull",
            )
            self._check_cancelled()

            self._emit_progress("Pushing DVC data", 78)
            self._run_network_op_with_retry(
                lambda: self.workspace.dvc.push(progress_cb=self._emit_progress),
                "DVC push",
            )
            self._check_cancelled()

            self._emit_progress("Pushing Git commit", 90)
            try:
                self._run_network_op_with_retry(
                    lambda: self.workspace.git.push(remote="origin", branch="main"),
                    "Git push",
                )
            except GitError as exc:
                if not self._is_non_fast_forward_error(str(exc)):
                    raise
                self._emit_progress("Remote moved, rebasing and retrying push", 94)
                self._run_network_op_with_retry(
                    lambda: self.workspace.git.pull(rebase=True),
                    "Git pull",
                )
                self._run_network_op_with_retry(
                    lambda: self.workspace.git.push(remote="origin", branch="main"),
                    "Git push",
                )

            self._emit_progress("Publish complete", 100)
            self._emit_finished(True, "Changes published.")
        except WorkflowCancelled as exc:
            self._emit_finished(False, str(exc))
        except Exception as exc:
            self._emit_error(str(exc))
            self._emit_finished(False, str(exc))
