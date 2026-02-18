from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def _load_registry(path: Path) -> dict:
    if not path.exists():
        return {"version": "1.0", "projects": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_registry(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _ensure_bare_repo(git_exe: str, repo_path: Path) -> None:
    if not (repo_path.exists() and (repo_path / "HEAD").exists()):
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([git_exe, "init", "--bare", str(repo_path)], check=True)

    # Keep default branch consistent for every new clone.
    subprocess.run(
        [git_exe, "--git-dir", str(repo_path), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
    )


def _dataset_entry(project_id: str, dataset_id: str) -> dict:
    pretty = dataset_id.replace("_", " ").title()
    return {
        "dataset_id": dataset_id,
        "name": pretty,
        "description": f"Dataset {dataset_id} for {project_id}",
        "source": "Factory Source",
    }


def setup(base_path: str, project_id: str, project_name: str, dataset_ids: list[str], git_exe: str) -> None:
    base = Path(base_path)
    git_remote = base / "git_remote" / f"{project_id}.git"
    dvc_remote = base / "dvc_remote" / project_id
    locks = base / "locks" / project_id
    registry_path = base / "registry" / "registry.json"

    dvc_remote.mkdir(parents=True, exist_ok=True)
    locks.mkdir(parents=True, exist_ok=True)
    _ensure_bare_repo(git_exe, git_remote)

    registry = _load_registry(registry_path)
    projects = registry.setdefault("projects", [])

    existing = next((p for p in projects if p.get("project_id") == project_id), None)
    if existing:
        known = {d.get("dataset_id") for d in existing.get("datasets", [])}
        for ds in dataset_ids:
            if ds not in known:
                existing.setdefault("datasets", []).append(_dataset_entry(project_id, ds))
        existing["name"] = project_name
        existing["git_remote"] = str(git_remote)
        existing["dvc_remote"] = str(dvc_remote)
    else:
        projects.append(
            {
                "project_id": project_id,
                "name": project_name,
                "description": f"Project {project_name}",
                "git_remote": str(git_remote),
                "dvc_remote": str(dvc_remote),
                "datasets": [_dataset_entry(project_id, ds) for ds in dataset_ids],
            }
        )

    _save_registry(registry_path, registry)

    print("DataGest server setup complete")
    print(f"Base path      : {base}")
    print(f"Git remote     : {git_remote}")
    print(f"DVC remote     : {dvc_remote}")
    print(f"Locks folder   : {locks}")
    print(f"Registry       : {registry_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize DataGest network share structure")
    parser.add_argument("--base-path", required=True, help="Base path, e.g. \\\\Server\\DataProjects")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--datasets", required=True, help="Comma-separated dataset IDs")
    parser.add_argument("--git-exe", default="git", help="Git executable path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_ids = [d.strip() for d in args.datasets.split(",") if d.strip()]
    if not dataset_ids:
        raise SystemExit("At least one dataset id is required")

    setup(
        base_path=args.base_path,
        project_id=args.project_id,
        project_name=args.project_name,
        dataset_ids=dataset_ids,
        git_exe=args.git_exe,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
