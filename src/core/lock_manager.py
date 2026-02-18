from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils.platform import get_machine_name, get_windows_username
from version import APP_VERSION


@dataclass(slots=True)
class LockInfo:
    dataset_id: str
    username: str
    machine: str
    timestamp: str
    app_version: str
    ttl_hours: float


class LockManager:
    def __init__(
        self,
        locks_root: Path,
        ttl_hours: float = 4.0,
        app_version: str = APP_VERSION,
        admin_mode: bool = False,
    ) -> None:
        self.locks_root = Path(locks_root)
        self.ttl_hours = ttl_hours
        self.app_version = app_version
        self.admin_mode = admin_mode
        self.username = get_windows_username()
        self.machine = get_machine_name()

    def _lock_path(self, project_id: str, dataset_id: str) -> Path:
        project_dir = self.locks_root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir / f"{dataset_id}.lock"

    def _read_lock_info(self, lock_path: Path) -> LockInfo | None:
        if not lock_path.exists():
            return None

        try:
            raw = json.loads(lock_path.read_text(encoding="utf-8"))
            return LockInfo(
                dataset_id=str(raw["dataset_id"]),
                username=str(raw["username"]),
                machine=str(raw["machine"]),
                timestamp=str(raw["timestamp"]),
                app_version=str(raw.get("app_version", "unknown")),
                ttl_hours=float(raw.get("ttl_hours", self.ttl_hours)),
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def _same_lock(self, left: LockInfo, right: LockInfo) -> bool:
        return (
            left.dataset_id == right.dataset_id
            and left.username == right.username
            and left.machine == right.machine
            and left.timestamp == right.timestamp
            and left.app_version == right.app_version
            and left.ttl_hours == right.ttl_hours
        )

    def _try_remove_stale_if_unchanged(self, lock_path: Path, expected: LockInfo) -> bool:
        current = self._read_lock_info(lock_path)
        if current is None:
            return False
        if not self._same_lock(current, expected):
            return False
        if not self.is_stale(current):
            return False

        try:
            lock_path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def check(self, project_id: str, dataset_id: str) -> LockInfo | None:
        lock_path = self._lock_path(project_id, dataset_id)
        return self._read_lock_info(lock_path)

    def is_stale(self, lock: LockInfo) -> bool:
        try:
            ts = datetime.fromisoformat(lock.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            return True

        age = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
        return age > timedelta(hours=lock.ttl_hours)

    def acquire(self, project_id: str, dataset_id: str) -> bool:
        lock_path = self._lock_path(project_id, dataset_id)
        lock_info = LockInfo(
            dataset_id=dataset_id,
            username=self.username,
            machine=self.machine,
            timestamp=datetime.now(timezone.utc).isoformat(),
            app_version=self.app_version,
            ttl_hours=self.ttl_hours,
        )
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY

        # At most one stale-cleanup retry: either we acquire immediately, or we
        # clear the exact stale lock observed and retry once.
        for _ in range(2):
            try:
                fd = os.open(str(lock_path), flags)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(asdict(lock_info), f, indent=2)
                return True
            except FileExistsError:
                existing = self._read_lock_info(lock_path)
                if existing is None or not self.is_stale(existing):
                    return False
                if not self._try_remove_stale_if_unchanged(lock_path, existing):
                    return False

        return False

    def release(self, project_id: str, dataset_id: str) -> bool:
        lock_path = self._lock_path(project_id, dataset_id)
        if not lock_path.exists():
            return True

        existing = self.check(project_id, dataset_id)
        if existing and not self.admin_mode:
            same_user = existing.username == self.username
            same_machine = existing.machine == self.machine
            if not (same_user and same_machine):
                return False

        try:
            lock_path.unlink()
            return True
        except OSError:
            return False

    def force_unlock(self, project_id: str, dataset_id: str) -> bool:
        lock_path = self._lock_path(project_id, dataset_id)
        if not lock_path.exists():
            return True
        try:
            lock_path.unlink()
            return True
        except OSError:
            return False
