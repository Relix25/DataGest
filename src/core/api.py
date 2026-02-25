from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Callable

import yaml

from core.git_manager import GitError
from core.lock_manager import LockManager
from core.workspace import WorkspaceManager, WorkspaceState
from models.project import CommitInfo, DatasetConfig, ProjectConfig
from utils.file_utils import clear_folder, copy_files, validate_image_folder

ProgressCB = Callable[[str, int], None]
ErrorCB = Callable[[str], None]
CancelCB = Callable[[], bool]


class CoreCancelled(RuntimeError):
    pass


@dataclass(slots=True)
class CoreStatus:
    project_id: str
    workspace_path: Path
    state: WorkspaceState
    branch: str | None
    clean: bool
    active_git_remote: str | None
    active_dvc_remote: str | None
    dataset_count: int


class DataGestCore:
    def __init__(self, workspace: WorkspaceManager, lock_manager: LockManager | None = None) -> None:
        self.workspace = workspace
        self.lock_manager = lock_manager

    def import_dataset(
        self,
        project: ProjectConfig,
        dataset: DatasetConfig,
        source_folder: Path,
        description: str | None = None,
        replace_dataset: bool = False,
        progress_cb: ProgressCB | None = None,
        error_cb: ErrorCB | None = None,
        cancel_cb: CancelCB | None = None,
    ) -> tuple[bool, str]:
        if self.lock_manager is None:
            raise RuntimeError("Import operation requires a lock manager.")

        lock_acquired = False
        try:
            self._emit_progress(progress_cb, cancel_cb, "Preparing workspace", 2)
            initialized = self.workspace.init_workspace(project)
            if not initialized:
                raise RuntimeError("Workspace initialization failed.")

            source = Path(source_folder)
            self._emit_progress(progress_cb, cancel_cb, "Validating image folder", 8)
            valid, message, file_count, _ = validate_image_folder(source)
            if not valid:
                raise RuntimeError(message)

            self._emit_progress(progress_cb, cancel_cb, "Acquiring dataset lock", 12)
            existing = self.lock_manager.check(project.project_id, dataset.dataset_id)
            if existing and not self.lock_manager.is_stale(existing):
                since = existing.timestamp
                try:
                    ts = datetime.fromisoformat(existing.timestamp)
                    since = ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                except ValueError:
                    pass
                raise RuntimeError(
                    f"Dataset locked by {existing.username} on {existing.machine} since {since}."
                )

            lock_acquired = self.lock_manager.acquire(project.project_id, dataset.dataset_id)
            if not lock_acquired:
                raise RuntimeError("Could not acquire dataset lock.")

            self._emit_progress(progress_cb, cancel_cb, "Synchronizing workspace", 20)
            self._run_network_op_with_retry(
                lambda: self.workspace.git.pull(rebase=True),
                "Git pull",
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
            self._check_cancelled(cancel_cb)
            self._run_network_op_with_retry(
                lambda: self.workspace.dvc.pull(progress_cb=progress_cb),
                "DVC pull",
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
            self._check_cancelled(cancel_cb)

            dataset_root = self.workspace.get_dataset_path(dataset.dataset_id)
            data_dir = dataset_root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)

            removed_count = 0
            if replace_dataset:
                self._emit_progress(progress_cb, cancel_cb, "Cleaning existing dataset files", 30)
                removed_count = clear_folder(data_dir)

            self._emit_progress(progress_cb, cancel_cb, "Copying image files", 40)
            copy_files(source, data_dir, progress_callback=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct))
            self._check_cancelled(cancel_cb)

            metadata = {
                "dataset_id": dataset.dataset_id,
                "name": dataset.name,
                "description": dataset.description,
                "source": dataset.source,
                "created": datetime.now(timezone.utc).isoformat(),
                "linked_models": [],
                "import_note": description or f"Import into {dataset.name}",
            }
            with (dataset_root / "dataset.yaml").open("w", encoding="utf-8") as f:
                yaml.safe_dump(metadata, f, sort_keys=False)

            rel_data = f"datasets/{dataset.dataset_id}/data"
            rel_dvc = f"datasets/{dataset.dataset_id}/data.dvc"
            rel_meta = f"datasets/{dataset.dataset_id}/dataset.yaml"

            self._emit_progress(progress_cb, cancel_cb, "Tracking data with DVC", 65)
            self.workspace.dvc.add(
                [rel_data],
                progress_cb=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct),
            )
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Creating commit", 80)
            workspace_root = dataset_root.parent.parent
            stage_candidates = [
                (rel_dvc, dataset_root / "data.dvc"),
                (rel_meta, dataset_root / "dataset.yaml"),
                (f"datasets/{dataset.dataset_id}/.gitignore", dataset_root / ".gitignore"),
                (".gitignore", workspace_root / ".gitignore"),
            ]
            stage_paths = [rel_path for rel_path, abs_path in stage_candidates if abs_path.exists()]
            if not stage_paths:
                raise RuntimeError("No files available to stage for commit.")
            self.workspace.git.add(stage_paths)

            commit_message = (
                f"Replace: {file_count} images into {dataset.name}"
                if replace_dataset
                else f"Import: {file_count} images into {dataset.name}"
            )

            has_changes = True
            try:
                self.workspace.git.commit(commit_message)
            except GitError as exc:
                if "nothing to commit" in str(exc).lower():
                    has_changes = False
                else:
                    raise

            if has_changes:
                self._emit_progress(progress_cb, cancel_cb, "Pushing data to DVC remote", 88)
                self._run_network_op_with_retry(
                    lambda: self.workspace.dvc.push(
                        progress_cb=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct)
                    ),
                    "DVC push",
                    progress_cb=progress_cb,
                    cancel_cb=cancel_cb,
                )
                self._check_cancelled(cancel_cb)
                self._emit_progress(progress_cb, cancel_cb, "Pushing commit to Git remote", 95)
                self._run_network_op_with_retry(
                    lambda: self.workspace.git.push(remote="origin", branch="main"),
                    "Git push",
                    progress_cb=progress_cb,
                    cancel_cb=cancel_cb,
                )
            else:
                self._emit_progress(progress_cb, cancel_cb, "No changes to push", 95)

            self._emit_progress(progress_cb, cancel_cb, "Import complete", 100)
            if replace_dataset:
                return (
                    True,
                    f"Replaced dataset with {file_count} images (removed {removed_count} previous files).",
                )
            if has_changes:
                return True, f"Imported and published {file_count} images."
            return True, "No dataset change detected; data already up to date."
        except CoreCancelled as exc:
            return False, str(exc)
        except Exception as exc:
            self._emit_error(error_cb, str(exc))
            return False, str(exc)
        finally:
            if lock_acquired:
                self.lock_manager.release(project.project_id, dataset.dataset_id)

    def fetch(
        self,
        project: ProjectConfig,
        allow_dirty: bool = False,
        progress_cb: ProgressCB | None = None,
        error_cb: ErrorCB | None = None,
        cancel_cb: CancelCB | None = None,
    ) -> tuple[bool, str]:
        try:
            self._emit_progress(progress_cb, cancel_cb, "Preparing workspace", 5)
            self.workspace.init_workspace(project)
            self._check_cancelled(cancel_cb)

            status = self.workspace.git.status()
            if not status.clean and not allow_dirty:
                raise RuntimeError(
                    "Workspace has local changes. Commit or discard them before fetching latest."
                )

            self._emit_progress(progress_cb, cancel_cb, "Pulling latest Git commits", 30)
            self._run_network_op_with_retry(
                lambda: self.workspace.git.pull(rebase=True),
                "Git pull",
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Pulling latest DVC objects", 55)
            self._run_network_op_with_retry(
                lambda: self.workspace.dvc.pull(
                    progress_cb=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct)
                ),
                "DVC pull",
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Checking out data", 80)
            self.workspace.dvc.checkout(
                progress_cb=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct)
            )

            branch = self.workspace.git.current_branch() or "detached"
            self._emit_progress(progress_cb, cancel_cb, "Fetch complete", 100)
            return True, f"Workspace synced on {branch}."
        except CoreCancelled as exc:
            return False, str(exc)
        except Exception as exc:
            self._emit_error(error_cb, str(exc))
            return False, str(exc)

    def publish(
        self,
        project: ProjectConfig,
        commit_message: str,
        dataset_id: str | None = None,
        paths_to_add: list[str] | None = None,
        progress_cb: ProgressCB | None = None,
        error_cb: ErrorCB | None = None,
        cancel_cb: CancelCB | None = None,
    ) -> tuple[bool, str]:
        try:
            self._emit_progress(progress_cb, cancel_cb, "Preparing workspace", 5)
            self.workspace.init_workspace(project)
            self._check_cancelled(cancel_cb)

            current_branch = self.workspace.git.current_branch()
            if current_branch is None:
                raise RuntimeError(
                    "Workspace is on a restored commit (detached HEAD). Return to latest before publishing."
                )

            if current_branch != "main":
                self._emit_progress(progress_cb, cancel_cb, "Switching to main", 10)
                self.workspace.git.checkout("main")
                self._check_cancelled(cancel_cb)

            add_paths = list(paths_to_add or ["."])
            if dataset_id:
                rel_data = f"datasets/{dataset_id}/data"
                rel_dataset = f"datasets/{dataset_id}"
                self._emit_progress(progress_cb, cancel_cb, "Tracking dataset changes with DVC", 18)
                self.workspace.dvc.add(
                    [rel_data],
                    progress_cb=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct),
                )
                add_paths = ["-A", rel_dataset]

            self._emit_progress(progress_cb, cancel_cb, "Staging files", 30)
            self.workspace.git.add(add_paths)
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Creating commit", 45)
            has_changes = True
            try:
                self.workspace.git.commit(commit_message)
            except GitError as exc:
                if "nothing to commit" in str(exc).lower():
                    has_changes = False
                else:
                    raise

            if not has_changes:
                self._emit_progress(progress_cb, cancel_cb, "No changes to publish", 100)
                return True, "No local change detected."

            self._emit_progress(progress_cb, cancel_cb, "Rebasing on latest main", 62)
            self._run_network_op_with_retry(
                lambda: self.workspace.git.pull(rebase=True),
                "Git pull",
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Pushing DVC data", 78)
            self._run_network_op_with_retry(
                lambda: self.workspace.dvc.push(
                    progress_cb=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct)
                ),
                "DVC push",
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Pushing Git commit", 90)
            try:
                self._run_network_op_with_retry(
                    lambda: self.workspace.git.push(remote="origin", branch="main"),
                    "Git push",
                    progress_cb=progress_cb,
                    cancel_cb=cancel_cb,
                )
            except GitError as exc:
                if not self._is_non_fast_forward_error(str(exc)):
                    raise
                self._emit_progress(progress_cb, cancel_cb, "Remote moved, rebasing and retrying push", 94)
                self._run_network_op_with_retry(
                    lambda: self.workspace.git.pull(rebase=True),
                    "Git pull",
                    progress_cb=progress_cb,
                    cancel_cb=cancel_cb,
                )
                self._run_network_op_with_retry(
                    lambda: self.workspace.git.push(remote="origin", branch="main"),
                    "Git push",
                    progress_cb=progress_cb,
                    cancel_cb=cancel_cb,
                )

            self._emit_progress(progress_cb, cancel_cb, "Publish complete", 100)
            return True, "Changes published."
        except CoreCancelled as exc:
            return False, str(exc)
        except Exception as exc:
            self._emit_error(error_cb, str(exc))
            return False, str(exc)

    def load_history(
        self,
        project: ProjectConfig,
        dataset_id: str,
        max_count: int = 50,
        progress_cb: ProgressCB | None = None,
        error_cb: ErrorCB | None = None,
        cancel_cb: CancelCB | None = None,
    ) -> tuple[bool, str, list[CommitInfo]]:
        commits: list[CommitInfo] = []
        try:
            self._emit_progress(progress_cb, cancel_cb, "Preparing workspace", 10)
            self.workspace.init_workspace(project)
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Loading history", 60)
            commits = self.workspace.git.log(path_filter=f"datasets/{dataset_id}", max_count=max_count)
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Analyzing image changes", 80)
            self._populate_image_deltas(dataset_id, commits)
            self._emit_progress(progress_cb, cancel_cb, "History loaded", 100)
            return True, f"Loaded {len(commits)} commits.", commits
        except CoreCancelled as exc:
            return False, str(exc), commits
        except Exception as exc:
            self._emit_error(error_cb, str(exc))
            return False, str(exc), commits

    def restore(
        self,
        project: ProjectConfig,
        commit_ref: str,
        progress_cb: ProgressCB | None = None,
        error_cb: ErrorCB | None = None,
        cancel_cb: CancelCB | None = None,
    ) -> tuple[bool, str]:
        try:
            self._emit_progress(progress_cb, cancel_cb, "Preparing workspace", 15)
            self.workspace.init_workspace(project)
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Checking out commit", 45)
            self.workspace.git.checkout(commit_ref)
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Restoring files with DVC", 75)
            self.workspace.dvc.checkout(
                progress_cb=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct)
            )
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Restore complete", 100)
            return True, f"Restored {commit_ref}"
        except CoreCancelled as exc:
            return False, str(exc)
        except Exception as exc:
            self._emit_error(error_cb, str(exc))
            return False, str(exc)

    def return_to_latest(
        self,
        project: ProjectConfig,
        progress_cb: ProgressCB | None = None,
        error_cb: ErrorCB | None = None,
        cancel_cb: CancelCB | None = None,
    ) -> tuple[bool, str]:
        try:
            self._emit_progress(progress_cb, cancel_cb, "Preparing workspace", 10)
            self.workspace.init_workspace(project)
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Checking out main", 30)
            self.workspace.git.checkout("main")
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Pulling latest Git", 50)
            self._run_network_op_with_retry(
                lambda: self.workspace.git.pull(rebase=True),
                "Git pull",
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Pulling latest DVC", 70)
            self._run_network_op_with_retry(
                lambda: self.workspace.dvc.pull(
                    progress_cb=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct)
                ),
                "DVC pull",
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Applying data checkout", 90)
            self.workspace.dvc.checkout(
                progress_cb=lambda msg, pct: self._emit_progress(progress_cb, cancel_cb, msg, pct)
            )
            self._check_cancelled(cancel_cb)

            self._emit_progress(progress_cb, cancel_cb, "Workspace on latest", 100)
            return True, "Returned to latest main"
        except CoreCancelled as exc:
            return False, str(exc)
        except Exception as exc:
            self._emit_error(error_cb, str(exc))
            return False, str(exc)

    def get_status(self, project: ProjectConfig) -> CoreStatus:
        self.workspace.init_workspace(project)
        git_status = self.workspace.git.status()
        state = self.workspace.get_state()
        datasets = self.workspace.list_datasets()
        return CoreStatus(
            project_id=project.project_id,
            workspace_path=self.workspace.workspace_path,
            state=state,
            branch=git_status.branch,
            clean=git_status.clean,
            active_git_remote=self.workspace.active_git_remote,
            active_dvc_remote=self.workspace.active_dvc_remote,
            dataset_count=len(datasets),
        )

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

    def _populate_image_deltas(self, dataset_id: str, commits: list[CommitInfo]) -> None:
        data_dvc = f"datasets/{dataset_id}/data.dvc"
        for commit in commits:
            current_nfiles = self._dvc_nfiles(self._git_show_file(commit.hash, data_dvc))
            parent_hash = self._first_parent(commit.hash)
            previous_nfiles = self._dvc_nfiles(self._git_show_file(parent_hash, data_dvc)) if parent_hash else 0

            if current_nfiles is None and previous_nfiles is None:
                commit.images_added = 0
                commit.images_removed = 0
                continue

            current = current_nfiles or 0
            previous = previous_nfiles or 0
            delta = current - previous
            commit.images_added = max(delta, 0)
            commit.images_removed = max(-delta, 0)

    def _check_cancelled(self, cancel_cb: CancelCB | None) -> None:
        if cancel_cb and cancel_cb():
            raise CoreCancelled("Cancelled by user.")

    def _emit_progress(
        self,
        progress_cb: ProgressCB | None,
        cancel_cb: CancelCB | None,
        message: str,
        percent: int,
    ) -> None:
        self._check_cancelled(cancel_cb)
        if progress_cb:
            progress_cb(message, max(0, min(100, percent)))

    def _emit_error(self, error_cb: ErrorCB | None, message: str) -> None:
        if error_cb:
            error_cb(message)

    def _is_non_fast_forward_error(self, message: str) -> bool:
        lowered = message.lower()
        return "non-fast-forward" in lowered or "failed to push some refs" in lowered

    def _is_retryable_network_error(self, message: str) -> bool:
        lowered = message.lower()
        markers = (
            "network",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "could not resolve host",
            "unable to access",
            "transport endpoint",
            "broken pipe",
            "resource busy",
            "name or service not known",
        )
        return any(marker in lowered for marker in markers)

    def _run_network_op_with_retry(
        self,
        operation: Callable[[], None],
        label: str,
        progress_cb: ProgressCB | None = None,
        cancel_cb: CancelCB | None = None,
        retries: int = 3,
    ) -> None:
        attempts = max(retries, 1)
        for attempt in range(1, attempts + 1):
            self._check_cancelled(cancel_cb)
            try:
                operation()
                return
            except CoreCancelled:
                raise
            except Exception as exc:
                is_last = attempt >= attempts
                retryable = self._is_retryable_network_error(str(exc))
                if is_last or not retryable:
                    raise

                delay = min(8.0, 0.75 * (2 ** (attempt - 1)))
                first_line = str(exc).splitlines()[0] if str(exc).strip() else "network error"
                self._emit_progress(
                    progress_cb,
                    cancel_cb,
                    f"{label} failed ({first_line}). Retrying in {delay:.1f}s (attempt {attempt + 1}/{attempts})",
                    0,
                )
                time.sleep(delay)
