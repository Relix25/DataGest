from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.lock_manager import LockInfo, LockManager


def test_lock_acquire_release(tmp_path: Path) -> None:
    lock = LockManager(tmp_path, ttl_hours=4.0)
    assert lock.acquire("p1", "d1") is True
    assert lock.acquire("p1", "d1") is False
    assert lock.release("p1", "d1") is True


def test_lock_stale_detection(tmp_path: Path) -> None:
    lock = LockManager(tmp_path, ttl_hours=1.0)
    old = LockInfo(
        dataset_id="d1",
        username="u",
        machine="m",
        timestamp=(datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
        app_version="0.1.0",
        ttl_hours=1.0,
    )
    assert lock.is_stale(old) is True


def test_lock_force_unlock(tmp_path: Path) -> None:
    lock = LockManager(tmp_path)
    assert lock.acquire("p1", "d1")
    assert lock.force_unlock("p1", "d1")
    assert lock.check("p1", "d1") is None


def test_lock_acquire_replaces_stale_lock(tmp_path: Path) -> None:
    lock = LockManager(tmp_path, ttl_hours=1.0)
    path = lock._lock_path("p1", "d1")
    stale = LockInfo(
        dataset_id="d1",
        username="u",
        machine="m",
        timestamp=(datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
        app_version="0.1.0",
        ttl_hours=1.0,
    )
    path.write_text(
        (
            "{\n"
            f'  "dataset_id": "{stale.dataset_id}",\n'
            f'  "username": "{stale.username}",\n'
            f'  "machine": "{stale.machine}",\n'
            f'  "timestamp": "{stale.timestamp}",\n'
            f'  "app_version": "{stale.app_version}",\n'
            f'  "ttl_hours": {stale.ttl_hours}\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    assert lock.acquire("p1", "d1") is True
    current = lock.check("p1", "d1")
    assert current is not None
    assert current.username == lock.username
    assert lock.is_stale(current) is False


def test_try_remove_stale_does_not_delete_changed_lock(tmp_path: Path) -> None:
    lock = LockManager(tmp_path, ttl_hours=1.0)
    path = lock._lock_path("p1", "d1")
    stale = LockInfo(
        dataset_id="d1",
        username="old-user",
        machine="old-machine",
        timestamp=(datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
        app_version="0.1.0",
        ttl_hours=1.0,
    )
    fresh = LockInfo(
        dataset_id="d1",
        username="new-user",
        machine="new-machine",
        timestamp=datetime.now(timezone.utc).isoformat(),
        app_version="0.1.0",
        ttl_hours=1.0,
    )

    path.write_text(
        (
            "{\n"
            f'  "dataset_id": "{stale.dataset_id}",\n'
            f'  "username": "{stale.username}",\n'
            f'  "machine": "{stale.machine}",\n'
            f'  "timestamp": "{stale.timestamp}",\n'
            f'  "app_version": "{stale.app_version}",\n'
            f'  "ttl_hours": {stale.ttl_hours}\n'
            "}\n"
        ),
        encoding="utf-8",
    )
    expected = lock._read_lock_info(path)
    assert expected is not None

    # Simulate another client replacing stale lock with a fresh one.
    path.write_text(
        (
            "{\n"
            f'  "dataset_id": "{fresh.dataset_id}",\n'
            f'  "username": "{fresh.username}",\n'
            f'  "machine": "{fresh.machine}",\n'
            f'  "timestamp": "{fresh.timestamp}",\n'
            f'  "app_version": "{fresh.app_version}",\n'
            f'  "ttl_hours": {fresh.ttl_hours}\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    assert lock._try_remove_stale_if_unchanged(path, expected) is False
    assert path.exists() is True
    current = lock._read_lock_info(path)
    assert current is not None
    assert current.username == "new-user"
