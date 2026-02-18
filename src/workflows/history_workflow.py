from __future__ import annotations

import re

from core.workspace import WorkspaceManager
from models.project import CommitInfo, ProjectConfig
from workflows.base import BaseWorkflow, Signal, WorkflowCancelled


class LoadHistoryWorkflow(BaseWorkflow):
    history_loaded = Signal(list)

    def __init__(
        self,
        project: ProjectConfig,
        dataset_id: str,
        workspace: WorkspaceManager,
        max_count: int = 50,
    ) -> None:
        super().__init__()
        self.project = project
        self.dataset_id = dataset_id
        self.workspace = workspace
        self.max_count = max_count
        self.commits: list[CommitInfo] = []

    def _dvc_nfiles(self, text: str | None) -> int | None:
        if not text:
            return None
        match = re.search(r"^\s*nfiles:\s*(\d+)\s*$", text, re.MULTILINE)
        if not match:
            return None
        return int(match.group(1))

    def _git_show_file(self, commit_hash: str, relative_path: str) -> str | None:
        try:
            return self.workspace.git.run(["show", f"{commit_hash}:{relative_path}"])
        except Exception:
            return None

    def _first_parent(self, commit_hash: str) -> str | None:
        try:
            output = self.workspace.git.run(["rev-list", "--parents", "-n", "1", commit_hash]).strip()
        except Exception:
            return None
        parts = output.split()
        return parts[1] if len(parts) > 1 else None

    def _populate_image_deltas(self) -> None:
        data_dvc = f"datasets/{self.dataset_id}/data.dvc"
        for commit in self.commits:
            current_nfiles = self._dvc_nfiles(self._git_show_file(commit.hash, data_dvc))
            parent_hash = self._first_parent(commit.hash)
            previous_nfiles = (
                self._dvc_nfiles(self._git_show_file(parent_hash, data_dvc))
                if parent_hash
                else 0
            )

            if current_nfiles is None and previous_nfiles is None:
                commit.images_added = 0
                commit.images_removed = 0
                continue

            current = current_nfiles or 0
            previous = previous_nfiles or 0
            delta = current - previous
            commit.images_added = max(delta, 0)
            commit.images_removed = max(-delta, 0)

    def execute(self) -> None:
        try:
            self._emit_progress("Preparing workspace", 10)
            self.workspace.init_workspace(self.project)
            self._check_cancelled()

            self._emit_progress("Loading history", 60)
            self.commits = self.workspace.git.log(
                path_filter=f"datasets/{self.dataset_id}", max_count=self.max_count
            )
            self._check_cancelled()
            self._emit_progress("Analyzing image changes", 80)
            self._populate_image_deltas()
            self.history_loaded.emit(self.commits)
            self._emit_progress("History loaded", 100)
            self._emit_finished(True, f"Loaded {len(self.commits)} commits.")
        except WorkflowCancelled as exc:
            self._emit_finished(False, str(exc))
        except Exception as exc:
            self._emit_error(str(exc))
            self._emit_finished(False, str(exc))


class RestoreVersionWorkflow(BaseWorkflow):
    def __init__(
        self,
        project: ProjectConfig,
        commit_ref: str,
        workspace: WorkspaceManager,
    ) -> None:
        super().__init__()
        self.project = project
        self.commit_ref = commit_ref
        self.workspace = workspace

    def execute(self) -> None:
        try:
            self._emit_progress("Preparing workspace", 15)
            self.workspace.init_workspace(self.project)
            self._check_cancelled()

            self._emit_progress("Checking out commit", 45)
            self.workspace.git.checkout(self.commit_ref)
            self._check_cancelled()

            self._emit_progress("Restoring files with DVC", 75)
            self.workspace.dvc.checkout(progress_cb=self._emit_progress)
            self._check_cancelled()

            self._emit_progress("Restore complete", 100)
            self._emit_finished(True, f"Restored {self.commit_ref}")
        except WorkflowCancelled as exc:
            self._emit_finished(False, str(exc))
        except Exception as exc:
            self._emit_error(str(exc))
            self._emit_finished(False, str(exc))


class ReturnToLatestWorkflow(BaseWorkflow):
    def __init__(self, project: ProjectConfig, workspace: WorkspaceManager) -> None:
        super().__init__()
        self.project = project
        self.workspace = workspace

    def execute(self) -> None:
        try:
            self._emit_progress("Preparing workspace", 10)
            self.workspace.init_workspace(self.project)
            self._check_cancelled()

            self._emit_progress("Checking out main", 30)
            self.workspace.git.checkout("main")
            self._check_cancelled()

            self._emit_progress("Pulling latest Git", 50)
            self._run_network_op_with_retry(
                lambda: self.workspace.git.pull(rebase=True),
                "Git pull",
            )
            self._check_cancelled()

            self._emit_progress("Pulling latest DVC", 70)
            self._run_network_op_with_retry(
                lambda: self.workspace.dvc.pull(progress_cb=self._emit_progress),
                "DVC pull",
            )
            self._check_cancelled()

            self._emit_progress("Applying data checkout", 90)
            self.workspace.dvc.checkout(progress_cb=self._emit_progress)
            self._check_cancelled()

            self._emit_progress("Workspace on latest", 100)
            self._emit_finished(True, "Returned to latest main")
        except WorkflowCancelled as exc:
            self._emit_finished(False, str(exc))
        except Exception as exc:
            self._emit_error(str(exc))
            self._emit_finished(False, str(exc))
