from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.lock_manager import LockManager
from core.workspace import WorkspaceManager
from models.project import DatasetConfig, ProjectConfig
from core.git_manager import GitError
from utils.file_utils import clear_folder, copy_files, validate_image_folder
from workflows.base import BaseWorkflow, WorkflowCancelled


class ImportWorkflow(BaseWorkflow):
    def __init__(
        self,
        project: ProjectConfig,
        dataset: DatasetConfig,
        source_folder: Path,
        workspace: WorkspaceManager,
        lock_manager: LockManager,
        description: str | None = None,
        replace_dataset: bool = False,
    ) -> None:
        super().__init__()
        self.project = project
        self.dataset = dataset
        self.source_folder = Path(source_folder)
        self.workspace = workspace
        self.lock_manager = lock_manager
        self.description = description or f"Import into {dataset.name}"
        self.replace_dataset = replace_dataset

    def execute(self) -> None:
        lock_acquired = False
        try:
            self._emit_progress("Preparing workspace", 2)
            initialized = self.workspace.init_workspace(self.project)
            if not initialized:
                raise RuntimeError("Workspace initialization failed.")

            self._emit_progress("Validating image folder", 8)
            valid, message, file_count, _ = validate_image_folder(self.source_folder)
            if not valid:
                raise RuntimeError(message)

            self._emit_progress("Acquiring dataset lock", 12)
            existing = self.lock_manager.check(self.project.project_id, self.dataset.dataset_id)
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

            lock_acquired = self.lock_manager.acquire(self.project.project_id, self.dataset.dataset_id)
            if not lock_acquired:
                raise RuntimeError("Could not acquire dataset lock.")

            self._emit_progress("Synchronizing workspace", 20)
            self._run_network_op_with_retry(
                lambda: self.workspace.git.pull(rebase=True),
                "Git pull",
            )
            self._check_cancelled()
            self._run_network_op_with_retry(
                lambda: self.workspace.dvc.pull(progress_cb=self._emit_progress),
                "DVC pull",
            )
            self._check_cancelled()

            dataset_root = self.workspace.get_dataset_path(self.dataset.dataset_id)
            data_dir = dataset_root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)

            removed_count = 0
            if self.replace_dataset:
                self._emit_progress("Cleaning existing dataset files", 30)
                removed_count = clear_folder(data_dir)

            self._emit_progress("Copying image files", 40)
            copy_files(self.source_folder, data_dir, progress_callback=self._emit_progress)
            self._check_cancelled()

            metadata = {
                "dataset_id": self.dataset.dataset_id,
                "name": self.dataset.name,
                "description": self.dataset.description,
                "source": self.dataset.source,
                "created": datetime.now(timezone.utc).isoformat(),
                "linked_models": [],
                "import_note": self.description,
            }
            with (dataset_root / "dataset.yaml").open("w", encoding="utf-8") as f:
                yaml.safe_dump(metadata, f, sort_keys=False)

            rel_data = f"datasets/{self.dataset.dataset_id}/data"
            rel_dvc = f"datasets/{self.dataset.dataset_id}/data.dvc"
            rel_meta = f"datasets/{self.dataset.dataset_id}/dataset.yaml"

            self._emit_progress("Tracking data with DVC", 65)
            self.workspace.dvc.add([rel_data], progress_cb=self._emit_progress)
            self._check_cancelled()

            self._emit_progress("Creating commit", 80)
            workspace_root = dataset_root.parent.parent
            stage_candidates = [
                (rel_dvc, dataset_root / "data.dvc"),
                (rel_meta, dataset_root / "dataset.yaml"),
                (f"datasets/{self.dataset.dataset_id}/.gitignore", dataset_root / ".gitignore"),
                (".gitignore", workspace_root / ".gitignore"),
            ]
            stage_paths = [
                rel_path
                for rel_path, abs_path in stage_candidates
                if abs_path.exists()
            ]
            if not stage_paths:
                raise RuntimeError("No files available to stage for commit.")
            self.workspace.git.add(stage_paths)

            commit_message = (
                f"Replace: {file_count} images into {self.dataset.name}"
                if self.replace_dataset
                else f"Import: {file_count} images into {self.dataset.name}"
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
                self._emit_progress("Pushing data to DVC remote", 88)
                self._run_network_op_with_retry(
                    lambda: self.workspace.dvc.push(progress_cb=self._emit_progress),
                    "DVC push",
                )
                self._check_cancelled()
                self._emit_progress("Pushing commit to Git remote", 95)
                self._run_network_op_with_retry(
                    lambda: self.workspace.git.push(remote="origin", branch="main"),
                    "Git push",
                )
            else:
                self._emit_progress("No changes to push", 95)

            self._emit_progress("Import complete", 100)
            if self.replace_dataset:
                self._emit_finished(
                    True,
                    (
                        f"Replaced dataset with {file_count} images "
                        f"(removed {removed_count} previous files)."
                    ),
                )
            elif has_changes:
                self._emit_finished(True, f"Imported and published {file_count} images.")
            else:
                self._emit_finished(True, "No dataset change detected; data already up to date.")
        except WorkflowCancelled as exc:
            self._emit_finished(False, str(exc))
        except Exception as exc:
            self._emit_error(str(exc))
            self._emit_finished(False, str(exc))
        finally:
            if lock_acquired:
                self.lock_manager.release(self.project.project_id, self.dataset.dataset_id)
