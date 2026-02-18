from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class DatasetConfig:
    dataset_id: str
    name: str
    description: str
    source: str


@dataclass(slots=True)
class ProjectConfig:
    project_id: str
    name: str
    description: str
    git_remote: str
    dvc_remote: str
    datasets: list[DatasetConfig] = field(default_factory=list)
    git_remote_sources: list[str] = field(default_factory=list)
    dvc_remote_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DatasetInfo:
    config: DatasetConfig
    file_count: int
    total_size_bytes: int
    last_updated: datetime | None
    last_author: str | None
    is_locked: bool
    locked_by: str | None
    local_state: str


@dataclass(slots=True)
class CommitInfo:
    hash: str
    short_hash: str
    author: str
    date: datetime
    message: str
    files_changed: int
    images_added: int = 0
    images_removed: int = 0
