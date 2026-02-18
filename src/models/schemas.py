from __future__ import annotations

REGISTRY_REQUIRED_KEYS = {
    "version",
    "projects",
}

PROJECT_REQUIRED_KEYS = {
    "project_id",
    "name",
    "description",
    "git_remote",
    "dvc_remote",
    "datasets",
}

DATASET_REQUIRED_KEYS = {
    "dataset_id",
    "name",
    "description",
    "source",
}

DATASET_YAML_REQUIRED_KEYS = {
    "dataset_id",
    "name",
    "description",
    "source",
    "created",
}
