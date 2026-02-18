from __future__ import annotations

import os
import re
import stat
import subprocess
import threading
from pathlib import Path
from typing import Callable, Sequence

from utils.platform import get_app_gitconfig_path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

ProgressCB = Callable[[str, int], None]


class DVCError(RuntimeError):
    pass


class DVCManager:
    def __init__(
        self,
        workspace_path: Path,
        dvc_executable: str | None = None,
        timeout_seconds: float = 1800.0,
    ) -> None:
        self.workspace = Path(workspace_path)
        self.dvc_exe = dvc_executable or "dvc"
        self.timeout_seconds = max(float(timeout_seconds), 0.0)

    def _inject_safe_directory_env(self, env: dict[str, str]) -> None:
        try:
            if not (self.workspace / ".git").exists():
                return
            safe_dir = self.workspace.resolve().as_posix()
        except OSError:
            return

        try:
            count = int(env.get("GIT_CONFIG_COUNT", "0"))
        except ValueError:
            count = 0

        env[f"GIT_CONFIG_KEY_{count}"] = "safe.directory"
        env[f"GIT_CONFIG_VALUE_{count}"] = safe_dir
        env["GIT_CONFIG_COUNT"] = str(count + 1)

    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        # Avoid background analytics writes that can fail on locked/read-only setups.
        env["DVC_NO_ANALYTICS"] = "1"
        app_global_cfg = get_app_gitconfig_path()
        if app_global_cfg is not None:
            env["GIT_CONFIG_GLOBAL"] = str(app_global_cfg)
        self._inject_safe_directory_env(env)
        return env

    def _run(self, args: Sequence[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.dvc_exe, *args],
            cwd=cwd or self.workspace,
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            env=self._base_env(),
            timeout=self.timeout_seconds if self.timeout_seconds > 0 else None,
            check=False,
        )

    def _run_checked(self, args: Sequence[str], cwd: Path | None = None) -> str:
        try:
            proc = self._run(args, cwd=cwd)
        except subprocess.TimeoutExpired as exc:
            timeout_text = (
                f"{self.timeout_seconds:.0f}s" if self.timeout_seconds > 0 else "configured timeout"
            )
            cmd_text = " ".join([self.dvc_exe, *args])
            raise DVCError(f"DVC command timed out after {timeout_text}: {cmd_text}") from exc
        if proc.returncode == 0:
            return proc.stdout.strip()

        message = proc.stderr.strip() or proc.stdout.strip() or "DVC command failed"
        if self._is_readonly_db_error(message):
            self._repair_local_state_db()
            proc = self._run(args, cwd=cwd)
            if proc.returncode == 0:
                return proc.stdout.strip()
            message = proc.stderr.strip() or proc.stdout.strip() or "DVC command failed"

        raise DVCError(message)

    def _run_stream(self, args: Sequence[str], progress_cb: ProgressCB | None = None) -> str:
        percent_re = re.compile(r"(\d{1,3})%")

        for attempt in range(2):
            proc = subprocess.Popen(
                [self.dvc_exe, *args],
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                env=self._base_env(),
            )
            timed_out = {"value": False}

            def watchdog() -> None:
                if self.timeout_seconds <= 0:
                    return
                try:
                    proc.wait(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out["value"] = True
                    try:
                        proc.kill()
                    except OSError:
                        pass

            guard = threading.Thread(target=watchdog, daemon=True)
            guard.start()

            output: list[str] = []
            assert proc.stdout is not None
            for line in proc.stdout:
                output.append(line.rstrip())
                if progress_cb:
                    try:
                        match = percent_re.search(line)
                        if match:
                            progress_cb(line.strip(), min(int(match.group(1)), 100))
                        else:
                            progress_cb(line.strip(), 0)
                    except Exception:
                        # Best-effort cancellation path: terminate the running DVC
                        # command when the progress callback requests an abort.
                        try:
                            proc.terminate()
                        except OSError:
                            pass
                        proc.wait()
                        raise

            rc = proc.wait()
            guard.join(timeout=0.1)
            text = "\n".join(output).strip()
            if timed_out["value"]:
                timeout_text = (
                    f"{self.timeout_seconds:.0f}s" if self.timeout_seconds > 0 else "configured timeout"
                )
                cmd_text = " ".join([self.dvc_exe, *args])
                raise DVCError(f"DVC command timed out after {timeout_text}: {cmd_text}")
            if rc == 0:
                return text

            if attempt == 0 and self._is_readonly_db_error(text):
                self._repair_local_state_db()
                if progress_cb:
                    progress_cb("Recovered DVC local state DB, retrying...", 0)
                continue

            raise DVCError(text or "DVC command failed")

        raise DVCError("DVC command failed")

    def _is_readonly_db_error(self, message: str) -> bool:
        lowered = message.lower()
        return "readonly database" in lowered or "read-only database" in lowered

    def _repair_local_state_db(self) -> None:
        tmp_dir = self.workspace / ".dvc" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        for path in tmp_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                path.chmod(stat.S_IREAD | stat.S_IWRITE)
            except OSError:
                continue

            if path.suffix.lower() in {".db", ".sqlite"} or self._is_sqlite_file(path):
                try:
                    path.unlink()
                except OSError:
                    pass

    def _is_sqlite_file(self, path: Path) -> bool:
        try:
            with path.open("rb") as f:
                header = f.read(16)
            return header.startswith(b"SQLite format 3")
        except OSError:
            return False

    def init(self) -> None:
        self._run_checked(["init", "-q"])

    def add(self, paths: list[str], progress_cb: ProgressCB | None = None) -> None:
        for path in paths:
            self._run_stream(["add", path], progress_cb=progress_cb)

    def push(self, progress_cb: ProgressCB | None = None) -> None:
        self._run_stream(["push"], progress_cb=progress_cb)

    def pull(self, progress_cb: ProgressCB | None = None) -> None:
        self._run_stream(["pull"], progress_cb=progress_cb)

    def checkout(self, progress_cb: ProgressCB | None = None) -> None:
        self._run_stream(["checkout"], progress_cb=progress_cb)

    def status(self) -> str:
        return self._run_checked(["status"])

    def set_default_remote(self, remote_name: str, remote_path: str) -> None:
        result = self._run(["remote", "list"])
        if result.returncode != 0:
            raise DVCError(result.stderr.strip() or "Failed to list DVC remotes")

        remote_names = {line.split()[0] for line in result.stdout.splitlines() if line.strip()}
        if remote_name in remote_names:
            self._run_checked(["remote", "modify", remote_name, "url", remote_path])
        else:
            self._run_checked(["remote", "add", "-d", remote_name, remote_path])
