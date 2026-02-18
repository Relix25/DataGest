from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.registry import RegistryError, RegistryLoader


def test_registry_load_ok(tmp_path: Path) -> None:
    registry = {
        "version": "1.0",
        "projects": [
            {
                "project_id": "p1",
                "name": "Project",
                "description": "desc",
                "git_remote": "g",
                "dvc_remote": "d",
                "datasets": [
                    {
                        "dataset_id": "d1",
                        "name": "Data",
                        "description": "desc",
                        "source": "cam",
                    }
                ],
            }
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    loader = RegistryLoader(str(path))
    projects = loader.load()
    assert len(projects) == 1
    assert projects[0].datasets[0].dataset_id == "d1"


def test_registry_missing_keys(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"projects": []}), encoding="utf-8")

    loader = RegistryLoader(str(path))
    with pytest.raises(RegistryError):
        loader.load()


def test_registry_optional_remote_sources(tmp_path: Path) -> None:
    registry = {
        "version": "1.0",
        "projects": [
            {
                "project_id": "p1",
                "name": "Project",
                "description": "desc",
                "git_remote": "g-primary",
                "dvc_remote": "d-primary",
                "git_remote_sources": ["g-secondary", "g-third"],
                "dvc_remote_sources": ["d-secondary"],
                "datasets": [
                    {
                        "dataset_id": "d1",
                        "name": "Data",
                        "description": "desc",
                        "source": "cam",
                    }
                ],
            }
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    loader = RegistryLoader(str(path))
    project = loader.load()[0]

    assert project.git_remote_sources == ["g-secondary", "g-third"]
    assert project.dvc_remote_sources == ["d-secondary"]


def test_registry_loader_uses_cache_until_reload(tmp_path: Path) -> None:
    first = {
        "version": "1.0",
        "projects": [
            {
                "project_id": "p1",
                "name": "Project One",
                "description": "desc",
                "git_remote": "g",
                "dvc_remote": "d",
                "datasets": [
                    {"dataset_id": "d1", "name": "Data", "description": "desc", "source": "cam"}
                ],
            }
        ],
    }
    second = {
        "version": "1.0",
        "projects": [
            {
                "project_id": "p1",
                "name": "Project Two",
                "description": "desc",
                "git_remote": "g",
                "dvc_remote": "d",
                "datasets": [
                    {"dataset_id": "d1", "name": "Data", "description": "desc", "source": "cam"}
                ],
            }
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(first), encoding="utf-8")

    loader = RegistryLoader(str(path))
    cached = loader.load()
    assert cached[0].name == "Project One"

    path.write_text(json.dumps(second), encoding="utf-8")

    still_cached = loader.load()
    assert still_cached[0].name == "Project One"

    reloaded = loader.reload()
    assert reloaded[0].name == "Project Two"


def test_registry_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text("{invalid json", encoding="utf-8")

    loader = RegistryLoader(str(path))
    with pytest.raises(RegistryError):
        loader.load()
