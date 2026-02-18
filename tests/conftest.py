from __future__ import annotations

import pytest

from models.project import DatasetConfig, ProjectConfig


@pytest.fixture
def project_factory():
    def _make(
        *,
        project_id: str = "p1",
        project_name: str = "P1",
        dataset_id: str = "d1",
        dataset_name: str = "D1",
        source: str = "src",
    ) -> ProjectConfig:
        dataset = DatasetConfig(dataset_id, dataset_name, "", source)
        return ProjectConfig(project_id, project_name, "", "", "", [dataset])

    return _make

