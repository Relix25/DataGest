from __future__ import annotations

from datetime import datetime
from enum import Enum
import logging
import shutil
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

import yaml

from core.protocols import DVCClient, GitClient
from core.git_manager import GitError
from models.project import DatasetConfig, DatasetInfo, ProjectConfig
from models.schemas import DATASET_YAML_REQUIRED_KEYS
from utils.file_utils import count_files
from utils.platform import get_machine_name, get_windows_username

logger = logging.getLogger(__name__)


class WorkspaceState(str, Enum):
    READY = "READY"
    DIRTY = "DIRTY"
    DETACHED = "DETACHED"
    CORRUPT = "CORRUPT"
    NOT_CLONED = "NOT_CLONED"


class WorkspaceManager:
    def __init__(self, root_path: Path, git: GitClient, dvc: DVCClient) -> None:
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self.git = git
        self.dvc = dvc
        self.current_project: ProjectConfig | None = None
        self.active_git_remote: str | None = None
        self.active_dvc_remote: str | None = None

    @property
    def workspace_path(self) -> Path:
        if not self.current_project:
            raise RuntimeError("No project selected")
        return self.root_path / self.current_project.project_id

    def _bind_workspace(self, path: Path) -> None:
        self.git.workspace = path
        self.dvc.workspace = path

    def _backup_invalid_workspace(self, workspace: Path) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for attempt in range(100):
            suffix = f"{stamp}" if attempt == 0 else f"{stamp}_{attempt:02d}"
            backup = workspace.with_name(f"{workspace.name}_corrupt_{suffix}")
            if backup.exists():
                continue
            try:
                workspace.rename(backup)
                return
            except OSError as exc:
                raise RuntimeError(f"Failed to backup invalid workspace {workspace}: {exc}") from exc
        raise RuntimeError(f"Failed to backup invalid workspace {workspace}: no available backup name")

    def _is_dubious_ownership_error(self, message: str) -> bool:
        lowered = message.lower()
        return "detected dubious ownership" in lowered

    def _ensure_safe_directory(self, workspace: Path) -> None:
        resolved = workspace.resolve()
        safe_dir = resolved.as_posix()
        known: set[str] = set()
        try:
            existing = self.git.run(
                ["config", "--global", "--get-all", "safe.directory"],
                cwd=self.root_path,
            )
            known = {line.strip() for line in existing.splitlines() if line.strip()}
        except GitError:
            # Best effort only: command-level safe.directory is still injected by GitManager.
            return

        known_lower = {entry.lower() for entry in known}
        if safe_dir.lower() in known_lower:
            return

        try:
            self.git.run(
                ["config", "--global", "--add", "safe.directory", safe_dir],
                cwd=self.root_path,
            )
        except GitError:
            # Some environments disallow writing global config; keep running with
            # per-command safe.directory injection.
            return

    def _git_remote_candidates(self, project: ProjectConfig) -> list[str]:
        candidates: list[str] = []
        for item in [project.git_remote, *project.git_remote_sources]:
            text = str(item).strip()
            if text and text not in candidates:
                candidates.append(text)
        return candidates

    def _dvc_remote_candidates(self, project: ProjectConfig) -> list[str]:
        candidates: list[str] = []
        for item in [project.dvc_remote, *project.dvc_remote_sources]:
            text = str(item).strip()
            if text and text not in candidates:
                candidates.append(text)
        return candidates

    def _local_path_from_remote(self, remote: str) -> Path | None:
        text = remote.strip()
        if text.startswith("file://"):
            parsed = urlparse(text)
            raw_path = unquote(parsed.path)
            if re.match(r"^/[a-zA-Z]:", raw_path):
                raw_path = raw_path[1:]
            return Path(raw_path)
        if text.startswith("\\\\") or re.match(r"^[a-zA-Z]:[\\/]", text):
            return Path(text)
        return None

    def _remote_path_accessible(self, remote: str) -> bool:
        local = self._local_path_from_remote(remote)
        if local is None:
            return True
        return local.exists()

    def _select_dvc_remote(self, project: ProjectConfig) -> str:
        candidates = self._dvc_remote_candidates(project)
        if not candidates:
            raise RuntimeError(f"No DVC remote configured for project {project.project_id}")
        for remote in candidates:
            if self._remote_path_accessible(remote):
                return remote
        return candidates[0]

    def _clone_with_fallback(self, project: ProjectConfig, workspace: Path) -> str:
        candidates = self._git_remote_candidates(project)
        if not candidates:
            raise RuntimeError(f"No Git remote configured for project {project.project_id}")

        errors: list[str] = []
        for remote in candidates:
            if not self._remote_path_accessible(remote):
                errors.append(f"{remote} (path inaccessible)")
                continue
            try:
                if workspace.exists():
                    shutil.rmtree(workspace, ignore_errors=True)
                self.git.clone(remote, workspace)
                return remote
            except GitError as exc:
                errors.append(f"{remote} -> {exc}")

        detail = "\n".join(errors) if errors else "No candidate remote available."
        raise RuntimeError(f"Unable to clone project {project.project_id} from configured sources:\n{detail}")

    def _has_commits(self) -> bool:
        try:
            self.git.run(["rev-parse", "--verify", "HEAD"])
            return True
        except GitError:
            return False

    def _remote_branch_exists(self, branch: str) -> bool:
        try:
            output = self.git.run(["ls-remote", "--heads", "origin", branch])
            return bool(output.strip())
        except GitError:
            return False

    def _checkout_main_base(self) -> None:
        if self._remote_branch_exists("main"):
            self.git.run(["fetch", "origin", "main"])
            self.git.run(["checkout", "-B", "main", "origin/main"])
        else:
            self.git.run(["checkout", "-B", "main"])

    def _push_main_with_recovery(self) -> None:
        try:
            self.git.push(remote="origin", branch="main")
            return
        except GitError as exc:
            msg = str(exc).lower()
            if "non-fast-forward" not in msg and "failed to push" not in msg:
                raise

        # Recovery path: rebase local commit on top of latest origin/main and retry push.
        self.git.run(["fetch", "origin", "main"])
        self.git.run(["rebase", "origin/main"])
        self.git.push(remote="origin", branch="main")

    def _bootstrap_initial_commit(self) -> None:
        # Create an initial commit so pull/fetch workflows are not blocked by an unborn branch.
        self._checkout_main_base()
        paths = [".dvc/config", ".dvc/.gitignore"]
        if (self.workspace_path / ".gitignore").exists():
            paths.append(".gitignore")
        self.git.add(paths)
        try:
            self.git.commit("Initialize DataGest workspace")
        except GitError as exc:
            if "nothing to commit" not in str(exc).lower():
                raise
        if self._remote_branch_exists("main"):
            self._push_main_with_recovery()
        else:
            # First push on an empty remote may require upstream setup.
            self.git.run(["push", "-u", "origin", "main"])

    def init_workspace(self, project: ProjectConfig) -> bool:
        self.current_project = project
        workspace = self.workspace_path
        self.active_dvc_remote = self._select_dvc_remote(project)

        if workspace.exists() and not (workspace / ".git").exists():
            self._backup_invalid_workspace(workspace)
            self.active_git_remote = self._clone_with_fallback(project, workspace)
        elif not workspace.exists():
            self.active_git_remote = self._clone_with_fallback(project, workspace)

        self._bind_workspace(workspace)

        if not (workspace / ".git").exists():
            raise RuntimeError(f"Invalid workspace: missing .git in {workspace}")

        # Required on shared/FAT/external filesystems where owner metadata is unavailable.
        self._ensure_safe_directory(workspace)

        # If git metadata exists but repository is unusable, backup and re-clone once.
        try:
            self.git.run(["rev-parse", "--is-inside-work-tree"])
        except GitError as exc:
            if self._is_dubious_ownership_error(str(exc)):
                # Retry once after forcing safe.directory in canonical form.
                self._ensure_safe_directory(workspace)
                self.git.run(["rev-parse", "--is-inside-work-tree"])
            else:
                self._backup_invalid_workspace(workspace)
                self.active_git_remote = self._clone_with_fallback(project, workspace)
                self._bind_workspace(workspace)
                self._ensure_safe_directory(workspace)
                self.git.run(["rev-parse", "--is-inside-work-tree"])

        if self.active_git_remote is None:
            try:
                self.active_git_remote = self.git.run(["remote", "get-url", "origin"])
            except GitError:
                self.active_git_remote = project.git_remote

        username = get_windows_username()
        machine = get_machine_name()
        self.git.run(["config", "user.name", username])
        self.git.run(["config", "user.email", f"{username}@{machine}"])
        self.git.run(["config", "core.longpaths", "true"])

        initialized_dvc = False
        if not (workspace / ".dvc").exists():
            self.dvc.init()
            initialized_dvc = True

        assert self.active_dvc_remote is not None
        self.dvc.set_default_remote("storage", self.active_dvc_remote)

        (workspace / "datasets").mkdir(parents=True, exist_ok=True)
        if initialized_dvc or not self._has_commits():
            self._bootstrap_initial_commit()

        return True

    def verify_integrity(self) -> bool:
        workspace = self.workspace_path
        if not (workspace / ".git").exists():
            return False
        if not (workspace / ".dvc").exists():
            return False

        try:
            self.git.run(["rev-parse", "--is-inside-work-tree"])
            return True
        except GitError:
            return False

    def get_state(self) -> WorkspaceState:
        workspace = self.workspace_path
        if not workspace.exists() or not (workspace / ".git").exists():
            return WorkspaceState.NOT_CLONED

        if not self.verify_integrity():
            return WorkspaceState.CORRUPT

        status = self.git.status()
        if status.detached:
            return WorkspaceState.DETACHED
        if not status.clean:
            return WorkspaceState.DIRTY
        return WorkspaceState.READY

    def get_dataset_path(self, dataset_id: str) -> Path:
        return self.workspace_path / "datasets" / dataset_id

    def list_datasets(self) -> list[DatasetInfo]:
        datasets_root = self.workspace_path / "datasets"
        if not datasets_root.exists():
            return []

        dvc_dirty_datasets = self._dvc_dirty_datasets()
        result: list[DatasetInfo] = []
        for dataset_dir in datasets_root.iterdir():
            if not dataset_dir.is_dir():
                continue

            meta_path = dataset_dir / "dataset.yaml"
            config: DatasetConfig
            if meta_path.exists():
                try:
                    loaded = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
                except yaml.YAMLError as exc:
                    logger.warning(
                        "Invalid dataset metadata YAML for '%s': %s",
                        dataset_dir.name,
                        exc,
                    )
                    loaded = {}
                raw = loaded if isinstance(loaded, dict) else {}
                missing = DATASET_YAML_REQUIRED_KEYS - raw.keys()
                if missing:
                    logger.warning(
                        "Dataset metadata missing keys for '%s': %s",
                        dataset_dir.name,
                        sorted(missing),
                    )
                config = DatasetConfig(
                    dataset_id=str(raw.get("dataset_id", dataset_dir.name)),
                    name=str(raw.get("name", dataset_dir.name)),
                    description=str(raw.get("description", "")),
                    source=str(raw.get("source", "")),
                )
            else:
                config = DatasetConfig(
                    dataset_id=dataset_dir.name,
                    name=dataset_dir.name,
                    description="",
                    source="",
                )

            data_dir = dataset_dir / "data"
            file_count, total_size = count_files(data_dir)

            last_updated = None
            last_author = None
            try:
                commits = self.git.log(path_filter=f"datasets/{dataset_dir.name}", max_count=1)
                if commits:
                    last_updated = commits[0].date
                    last_author = commits[0].author
            except GitError as exc:
                logger.debug("Failed to read git history for dataset '%s': %s", dataset_dir.name, exc)

            local_state = "not_downloaded" if not data_dir.exists() else "clean"
            if dataset_dir.name in dvc_dirty_datasets:
                local_state = "modified"
            result.append(
                DatasetInfo(
                    config=config,
                    file_count=file_count,
                    total_size_bytes=total_size,
                    last_updated=last_updated,
                    last_author=last_author,
                    is_locked=False,
                    locked_by=None,
                    local_state=local_state,
                )
            )
        return result

    def _dvc_dirty_datasets(self) -> set[str]:
        try:
            raw = self.dvc.status()
        except Exception as exc:
            logger.warning("Failed to get DVC status for workspace '%s': %s", self.workspace_path, exc)
            return set()

        dirty: set[str] = set()
        for line in raw.splitlines():
            normalized = line.strip().replace("\\", "/")
            match = re.search(r"datasets/([^/]+)/", normalized)
            if match:
                dirty.add(match.group(1))
        return dirty
