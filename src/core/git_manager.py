from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from models.project import CommitInfo
from utils.platform import get_app_gitconfig_path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class GitError(RuntimeError):
    pass


@dataclass(slots=True)
class GitStatus:
    clean: bool
    detached: bool
    branch: str | None
    raw: str


class GitManager:
    def __init__(
        self,
        workspace_path: Path,
        git_executable: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.workspace = Path(workspace_path)
        self.git_exe = git_executable or "git"
        self.timeout_seconds = max(float(timeout_seconds), 0.0)

    def _normalize_remote_url(self, remote_url: str) -> str:
        # Keep UNC paths as-is; convert local Windows drive paths to file:// URLs.
        if remote_url.startswith("\\\\"):
            return remote_url
        if re.match(r"^[a-zA-Z]:[\\/]", remote_url):
            return Path(remote_url).as_uri()
        return remote_url

    def _effective_cwd(self, cwd: Path | None) -> Path:
        return Path(cwd) if cwd is not None else self.workspace

    def _safe_directory_for_cwd(self, cwd: Path) -> str | None:
        # Shared/external filesystems may not expose ownership metadata; Git blocks
        # commands there unless the path is trusted.
        try:
            if (cwd / ".git").exists():
                return cwd.resolve().as_posix()
        except OSError:
            return None
        return None

    def _run(self, args: Sequence[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        app_global_cfg = get_app_gitconfig_path()
        if app_global_cfg is not None:
            env["GIT_CONFIG_GLOBAL"] = str(app_global_cfg)

        run_cwd = self._effective_cwd(cwd)
        cmd = [self.git_exe]
        safe_dir = self._safe_directory_for_cwd(run_cwd)
        if safe_dir:
            cmd.extend(["-c", f"safe.directory={safe_dir}"])
        cmd.extend(args)

        return subprocess.run(
            cmd,
            cwd=run_cwd,
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            env=env,
            timeout=self.timeout_seconds if self.timeout_seconds > 0 else None,
            check=False,
        )

    def run(self, args: Sequence[str], cwd: Path | None = None) -> str:
        try:
            proc = self._run(args, cwd=cwd)
        except subprocess.TimeoutExpired as exc:
            timeout_text = (
                f"{self.timeout_seconds:.0f}s" if self.timeout_seconds > 0 else "configured timeout"
            )
            cmd_text = " ".join([self.git_exe, *args])
            raise GitError(f"Git command timed out after {timeout_text}: {cmd_text}") from exc
        if proc.returncode != 0:
            raise GitError(proc.stderr.strip() or proc.stdout.strip() or "Git command failed")
        return proc.stdout.strip()

    def clone(self, remote_url: str, target_path: Path) -> None:
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = self._normalize_remote_url(remote_url)
        self.run(["clone", normalized, str(target_path)], cwd=target_path.parent)

    def add(self, paths: list[str]) -> None:
        if not paths:
            return
        self.run(["add", *paths])

    def commit(self, message: str, author: str | None = None) -> None:
        args = ["commit", "-m", message]
        if author:
            args.extend(["--author", author])
        self.run(args)

    def push(self, remote: str = "origin", branch: str = "main") -> None:
        self.run(["push", remote, branch])

    def pull(self, rebase: bool = True) -> None:
        args = ["pull"]
        if rebase:
            args.append("--rebase")
        self.run(args)

    def checkout(self, ref: str) -> None:
        self.run(["checkout", ref])

    def current_branch(self) -> str | None:
        branch = self.run(["rev-parse", "--abbrev-ref", "HEAD"])
        if branch == "HEAD":
            return None
        return branch

    def status(self) -> GitStatus:
        raw = self.run(["status", "--porcelain", "--branch"])
        lines = [line for line in raw.splitlines() if line.strip()]
        branch_line = lines[0] if lines else ""
        branch: str | None = None
        detached = "HEAD (no branch)" in branch_line or branch_line.startswith("## HEAD")
        if branch_line.startswith("## "):
            branch_name = branch_line[3:].split("...")[0].strip()
            if branch_name and branch_name != "HEAD":
                branch = branch_name
        clean = len(lines) <= 1
        return GitStatus(clean=clean, detached=detached, branch=branch, raw=raw)

    def log(self, path_filter: str | None = None, max_count: int = 50) -> list[CommitInfo]:
        pretty = "%H%x1f%h%x1f%an%x1f%aI%x1f%s"
        args = [
            "log",
            f"-n{max_count}",
            f"--pretty=format:{pretty}",
            "--name-only",
            "--date=iso-strict",
        ]
        if path_filter:
            args.extend(["--", path_filter])

        raw = self.run(args)
        commits: list[CommitInfo] = []

        current_header: tuple[str, str, str, str, str] | None = None
        current_files: list[str] = []

        def flush() -> None:
            if not current_header:
                return
            commit_hash, short_hash, author, date_str, message = current_header
            commits.append(
                CommitInfo(
                    hash=commit_hash,
                    short_hash=short_hash,
                    author=author,
                    date=datetime.fromisoformat(date_str),
                    message=message,
                    files_changed=len(current_files),
                )
            )

        for line in raw.splitlines():
            text = line.strip().replace("\x1e", "")
            if not text:
                continue
            if "\x1f" in text:
                flush()
                parts = text.split("\x1f")
                if len(parts) < 5:
                    current_header = None
                    current_files = []
                    continue
                current_header = (parts[0], parts[1], parts[2], parts[3], parts[4])
                current_files = []
            elif current_header:
                current_files.append(text)

        flush()
        return commits
