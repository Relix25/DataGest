# DataGest

Desktop application for factory image dataset versioning on top of Git + DVC.

## Phase 0 Scope

- Single selected project from shared registry
- Multiple datasets per project
- Import folder into dataset (optional)
- Workspace-first flow: edit files in local workspace, then commit/push changes
- Fetch latest, view history, restore a version, return to latest
- No terminal required for operators

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python src/main.py
```

## Tests

```powershell
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Build

```powershell
pip install -e ".[dev]"
.\packaging\build.ps1
```

## Workspace-first Flow (GitHub Desktop style)

1. Select a dataset, then click `Open Folder`.
2. Add/remove/update files directly in `datasets/<dataset_id>/data`.
3. Click `Commit & Push` in DataGest.
4. Enter a commit message.

DataGest will run DVC tracking for that dataset, stage additions/deletions, create a commit, and push DVC + Git.

Dataset list supports search by dataset name, id, and source.

History is available in the dedicated `History` tab, auto-refreshes when dataset context changes, and supports expandable commit entries with image `+/-` deltas.

## Options

- Use `Options` in the top bar to change the local workspace root path.
- The value is saved in `%LOCALAPPDATA%\DataGest\config.yaml`.
- Use `Options` to manage multiple registry sources (one path per line).
- Use the registry dropdown (left of `Reload Registry`) to choose the active registry source.

## Multiple Shared Repo Sources

Each project in `registry.json` can define fallback shared-disk sources:

```json
{
  "project_id": "defect_line_a",
  "git_remote": "\\\\ServerA\\DataProjects\\git_remote\\defect_line_a.git",
  "dvc_remote": "\\\\ServerA\\DataProjects\\dvc_remote\\defect_line_a",
  "git_remote_sources": [
    "\\\\ServerB\\DataProjects\\git_remote\\defect_line_a.git"
  ],
  "dvc_remote_sources": [
    "\\\\ServerB\\DataProjects\\dvc_remote\\defect_line_a"
  ]
}
```

DataGest will try these sources in order and use the first accessible one.

## Network Setup

Initialize share structure once:

```powershell
python scripts/setup_server.py --base-path "\\Server\DataProjects" --project-id defect_line_a --project-name "Defect Line A" --datasets camera_1,camera_2
```

## Local Shared Setup Example (`H:\Dev\DataGest_repo`)

Initialize the shared repo structure at `H:\Dev\DataGest_repo`:

```powershell
python scripts/setup_server.py --base-path "H:\Dev\DataGest_repo" --project-id defect_line_a --project-name "Defect Line A" --datasets camera_1,camera_2 --git-exe "C:\Program Files\Git\cmd\git.exe"
```

Then in DataGest:

1. Open `Options`.
2. In `Registry sources`, add `H:\Dev\DataGest_repo\registry\registry.json` (one line).
3. Save.
4. Use the registry dropdown (left of `Reload Registry`) and select `H:\Dev\DataGest_repo\registry\registry.json`.
