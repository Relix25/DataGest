from __future__ import annotations
# ruff: noqa: E402

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.api import DataGestCore
from core.config import load_config
from core.dvc_manager import DVCManager
from core.git_manager import GitManager
from core.lock_manager import LockManager
from core.registry import RegistryLoader
from core.tool_bootstrap import ToolBootstrap
from core.workspace import WorkspaceManager
from models.project import ProjectConfig


def _progress_printer(message: str, percent: int) -> None:
    width = 30
    clamped = max(0, min(100, percent))
    filled = int(width * clamped / 100)
    bar = "#" * filled + "-" * (width - filled)
    line = f"\r[{bar}] {clamped:3d}% {message[:80]}"
    sys.stdout.write(line)
    sys.stdout.flush()
    if clamped >= 100:
        sys.stdout.write("\n")
        sys.stdout.flush()


def _error_printer(message: str) -> None:
    if not message:
        return
    if not message.endswith("\n"):
        message = f"{message}\n"
    sys.stderr.write(message)
    sys.stderr.flush()


def _build_core() -> tuple[DataGestCore, list[ProjectConfig]]:
    config = load_config()
    bootstrap = ToolBootstrap(config)

    git_exe = shutil.which("git") or config.git_executable
    dvc_exe = shutil.which("dvc") or config.dvc_executable

    if not git_exe:
        git_exe = str(bootstrap.ensure_git())
    if not dvc_exe:
        dvc_exe = str(bootstrap.ensure_dvc())

    root = Path(config.workspace_root)
    git_manager = GitManager(
        root,
        git_executable=git_exe,
        timeout_seconds=config.git_timeout_seconds,
    )
    dvc_manager = DVCManager(
        root,
        dvc_executable=dvc_exe,
        timeout_seconds=config.dvc_timeout_seconds,
    )
    workspace = WorkspaceManager(root, git_manager, dvc_manager)
    lock_manager = LockManager(
        Path(config.locks_path),
        ttl_hours=config.lock_ttl_hours,
        admin_mode=config.admin_mode,
    )
    core = DataGestCore(workspace, lock_manager)

    projects = RegistryLoader(config.registry_path).load()
    return core, projects


def _select_project(projects: list[ProjectConfig], project_id: str | None) -> ProjectConfig:
    if not projects:
        raise RuntimeError("No project found in registry.")

    if project_id:
        for project in projects:
            if project.project_id == project_id:
                return project
        raise RuntimeError(f"Project '{project_id}' not found in registry.")

    if len(projects) == 1:
        return projects[0]

    ids = ", ".join(project.project_id for project in projects)
    raise RuntimeError(f"Multiple projects found ({ids}). Pass --project.")


def _run_status(args: argparse.Namespace) -> int:
    core, projects = _build_core()
    project = _select_project(projects, args.project)
    status = core.get_status(project)

    print(f"Project: {status.project_id}")
    print(f"Workspace: {status.workspace_path}")
    print(f"State: {status.state.value}")
    print(f"Branch: {status.branch or 'detached'}")
    print(f"Clean: {status.clean}")
    print(f"Datasets: {status.dataset_count}")
    print(f"Git remote: {status.active_git_remote or 'unknown'}")
    print(f"DVC remote: {status.active_dvc_remote or 'unknown'}")
    return 0


def _run_sync(args: argparse.Namespace) -> int:
    core, projects = _build_core()
    project = _select_project(projects, args.project)

    success, message = core.fetch(
        project=project,
        allow_dirty=args.allow_dirty,
        progress_cb=_progress_printer,
        error_cb=_error_printer,
    )
    if not success:
        print(f"\nFetch failed: {message}", file=sys.stderr)
        return 1

    print(f"Fetch: {message}")
    if args.fetch_only:
        return 0

    success, message = core.publish(
        project=project,
        commit_message=args.message,
        dataset_id=args.dataset_id,
        paths_to_add=args.path or ["."],
        progress_cb=_progress_printer,
        error_cb=_error_printer,
    )
    if not success:
        print(f"\nPublish failed: {message}", file=sys.stderr)
        return 1

    print(f"Publish: {message}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="datagest", description="DataGest headless CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show workspace state for a project")
    status_parser.add_argument("--project", help="Project ID (optional when registry has one project)")
    status_parser.set_defaults(handler=_run_status)

    sync_parser = subparsers.add_parser("sync", help="Fetch and optionally publish workspace changes")
    sync_parser.add_argument("--project", help="Project ID (optional when registry has one project)")
    sync_parser.add_argument("--allow-dirty", action="store_true", help="Allow fetch when workspace is dirty")
    sync_parser.add_argument("--fetch-only", action="store_true", help="Only run fetch, skip publish")
    sync_parser.add_argument("--dataset-id", help="Publish only a specific dataset")
    sync_parser.add_argument(
        "--message",
        default="CLI sync update",
        help="Commit message used for publish",
    )
    sync_parser.add_argument(
        "--path",
        action="append",
        default=None,
        help="Path to stage during publish (repeatable)",
    )
    sync_parser.set_defaults(handler=_run_sync)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
