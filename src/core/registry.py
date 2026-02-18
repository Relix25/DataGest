from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from models.project import DatasetConfig, ProjectConfig
from models.schemas import DATASET_REQUIRED_KEYS, PROJECT_REQUIRED_KEYS, REGISTRY_REQUIRED_KEYS


class RegistryError(RuntimeError):
    pass


@dataclass(slots=True)
class RegistrySnapshot:
    version: str
    projects: list[ProjectConfig]


class RegistryLoader:
    def __init__(self, registry_path: str) -> None:
        self.registry_path = Path(registry_path)
        self._cached: RegistrySnapshot | None = None

    def _read(self) -> dict:
        if not self.registry_path.exists():
            raise RegistryError(f"Registry not found: {self.registry_path}")
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RegistryError(f"Invalid registry JSON: {exc}") from exc

    def _validate(self, raw: dict) -> None:
        missing = REGISTRY_REQUIRED_KEYS - raw.keys()
        if missing:
            raise RegistryError(f"Registry missing keys: {sorted(missing)}")
        if not isinstance(raw.get("projects"), list):
            raise RegistryError("Registry 'projects' must be a list")

    def _parse_project(self, raw: dict) -> ProjectConfig:
        missing = PROJECT_REQUIRED_KEYS - raw.keys()
        if missing:
            raise RegistryError(
                f"Project {raw.get('project_id', '<unknown>')} missing keys: {sorted(missing)}"
            )

        git_remote_sources_raw = raw.get("git_remote_sources", [])
        dvc_remote_sources_raw = raw.get("dvc_remote_sources", [])
        if not isinstance(git_remote_sources_raw, list):
            raise RegistryError(f"Project {raw['project_id']} field 'git_remote_sources' must be a list")
        if not isinstance(dvc_remote_sources_raw, list):
            raise RegistryError(f"Project {raw['project_id']} field 'dvc_remote_sources' must be a list")

        datasets: list[DatasetConfig] = []
        for ds in raw.get("datasets", []):
            ds_missing = DATASET_REQUIRED_KEYS - ds.keys()
            if ds_missing:
                raise RegistryError(
                    f"Dataset in project {raw['project_id']} missing keys: {sorted(ds_missing)}"
                )
            datasets.append(
                DatasetConfig(
                    dataset_id=str(ds["dataset_id"]),
                    name=str(ds["name"]),
                    description=str(ds["description"]),
                    source=str(ds["source"]),
                )
            )

        return ProjectConfig(
            project_id=str(raw["project_id"]),
            name=str(raw["name"]),
            description=str(raw["description"]),
            git_remote=str(raw["git_remote"]),
            dvc_remote=str(raw["dvc_remote"]),
            datasets=datasets,
            git_remote_sources=[str(item) for item in git_remote_sources_raw if str(item).strip()],
            dvc_remote_sources=[str(item) for item in dvc_remote_sources_raw if str(item).strip()],
        )

    def load(self, use_cache: bool = True) -> list[ProjectConfig]:
        if use_cache and self._cached is not None:
            return list(self._cached.projects)

        raw = self._read()
        self._validate(raw)

        projects = [self._parse_project(p) for p in raw["projects"]]
        self._cached = RegistrySnapshot(version=str(raw["version"]), projects=projects)
        return list(projects)

    def reload(self) -> list[ProjectConfig]:
        self._cached = None
        return self.load(use_cache=False)
