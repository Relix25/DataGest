from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from models.project import CommitInfo


@runtime_checkable
class GitClient(Protocol):
    workspace: Path

    def clone(self, remote_url: str, target_path: Path) -> None:
        ...

    def run(self, args, cwd: Path | None = None) -> str:
        ...

    def add(self, paths: list[str]) -> None:
        ...

    def commit(self, message: str, author: str | None = None) -> None:
        ...

    def push(self, remote: str = "origin", branch: str = "main") -> None:
        ...

    def pull(self, rebase: bool = True) -> None:
        ...

    def checkout(self, ref: str) -> None:
        ...

    def current_branch(self) -> str | None:
        ...

    def status(self):
        ...

    def log(self, path_filter: str | None = None, max_count: int = 50) -> list[CommitInfo]:
        ...


@runtime_checkable
class DVCClient(Protocol):
    workspace: Path

    def init(self) -> None:
        ...

    def add(self, paths: list[str], progress_cb=None) -> None:
        ...

    def push(self, progress_cb=None) -> None:
        ...

    def pull(self, progress_cb=None) -> None:
        ...

    def checkout(self, progress_cb=None) -> None:
        ...

    def status(self) -> str:
        ...

    def set_default_remote(self, remote_name: str, remote_path: str) -> None:
        ...

