# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- _Nothing yet._

## [0.5.1] - 2026-02-18

### Fixed
- GitHub release pipeline now packages the PyInstaller `dist/DataGest` output as
  `DataGest-vX.Y.Z.zip` and attaches it explicitly to the GitHub Release.
- Release job now fails if the expected artifact file is missing, preventing
  silent releases with only source archives.

## [0.5.0] - 2026-02-18

### Added
- Dataset metadata validation during workspace listing now checks required keys from
  `DATASET_YAML_REQUIRED_KEYS` and logs actionable warnings when metadata is incomplete.
- New workspace tests for dataset metadata parsing robustness:
  missing required keys and invalid YAML payloads.

### Changed
- Type annotations in `models/project.py` now consistently use `X | None` syntax instead of `Optional[X]`.
- `ROADMAP.md` now marks all P3 items complete; the execution plan is fully closed.

### Fixed
- Invalid `dataset.yaml` files no longer fail silently during dataset discovery; fallback parsing is applied with explicit warnings.
- Incomplete `dataset.yaml` entries now surface missing key warnings instead of remaining implicit.

## [0.4.0] - 2026-02-18

### Added
- Shared pytest fixtures in `tests/conftest.py` to reduce duplicated workflow/project setup.
- New protocol contract tests for Git/DVC manager implementations.
- Utility helper `get_app_gitconfig_path()` in `utils.platform` for centralized app gitconfig resolution.

### Changed
- Application versioning is now centralized in `src/version.py` (`APP_VERSION`) and reused by UI/About, lock metadata defaults, and package metadata.
- `WorkspaceManager` now depends on protocol interfaces (`GitClient`/`DVCClient`) instead of concrete manager classes.
- `RegistryLoader` now has explicit cache behavior (`load(use_cache=True)`) and `reload()` forces a fresh read.
- CI/build dependency installation now uses `pyproject.toml` extras (`pip install -e .[dev]`) instead of a duplicated requirements file.
- Build script now derives the release zip version automatically from `APP_VERSION` when no explicit version is passed.
- README setup/build instructions are aligned with the `pyproject.toml` workflow.

### Fixed
- `validate_unc_path()` now validates real UNC syntax and exposes `must_exist` semantics; it no longer accepts local paths as UNC.
- Removed duplicated app-global Git config path logic from Git and DVC managers through shared utility usage.

## [0.3.0] - 2026-02-18

### Added
- Configurable subprocess timeout policy through app config:
  `git_timeout_seconds` and `dvc_timeout_seconds`.
- Additional workflow test coverage for destructive flows:
  `FetchLatestWorkflow`, `RestoreVersionWorkflow`, and `ReturnToLatestWorkflow`
  (success, guard, and failure paths).
- Retry/backoff validation test for transient network pull errors.

### Changed
- Workflow-to-UI signal wiring now uses explicit Qt queued connections for progress,
  error, finished, and history-loaded updates.
- Workflow network operations now use bounded retry with exponential backoff for
  transient UNC/network failures (Git/DVC pull/push paths).
- Application shutdown now guards active worker threads with cancel-and-wait flow.

### Fixed
- Removed inline cross-thread UI error lambda in favor of dedicated UI slots.
- Git and DVC command wrappers now enforce timeout on subprocess execution and
  return clear timeout errors.
- DVC streaming operations now enforce timeout with watchdog termination for stuck
  commands.
- Options save flow now defensively handles empty registry source lists and prevents
  `IndexError` in edge cases.
- Workspace dataset status no longer swallows DVC errors silently; failures are now
  logged for diagnostics.
- Added logging for git-history lookup failures during dataset listing.

## [0.2.0] - 2026-02-18

### Added
- Import dialog now includes a `Replace dataset content` mode to mirror the source folder and remove obsolete files from the dataset.
- New `Options` dialog to update `workspace_root` from the UI without editing config files manually.
- `Options` now lets operators manage multiple registry sources directly.
- Dataset list now includes a search box (name, dataset id, and source).
- Project registry now supports fallback Git/DVC repo sources (`git_remote_sources`, `dvc_remote_sources`) for shared-disk failover.
- History tab now refreshes automatically on dataset selection and when returning to the tab.
- History entries are now expandable and show commit details with image deltas (`+/-`) computed from DVC `nfiles`.
- Restore now requires explicit confirmation before checking out a historical commit.

### Changed
- Workflow cancellation is now handled as a first-class runtime state (`Cancelled by user`) instead of being ignored.
- Workflows now stop between heavy steps when cancellation is requested, before commit/push side effects.
- Roadmap execution tracking now marks completed items directly in `ROADMAP.md`.

### Fixed
- Import workflow no longer stages a missing root `.gitignore`, preventing `fatal: pathspec '.gitignore' did not match any files`.
- Commit staging during import now includes only files that actually exist.
- DVC command execution now retries once after repairing local `.dvc/tmp` SQLite state when hitting `attempt to write a readonly database`.
- DVC analytics is disabled in app-managed subprocess environments to reduce background DB write failures.
- DVC subprocess environments now inherit app-owned Git config and inject `safe.directory`, avoiding shared-drive ownership failures.
- DVC streaming commands now terminate their subprocess when a progress callback aborts (cancel path).
- Import workflow now treats `nothing to commit` as a successful no-op instead of failing the operation.
- Dataset publish flow now handles local add/delete edits from the workspace by running `dvc add` and `git add -A` on the dataset before commit/push.
- Publish now fails fast on detached HEAD with a clear message to return to latest first.
- Reverted unintended import metadata editing of dataset `source`; import now keeps source from registry config.
- Workspace initialization now auto-registers the repo path in Git `safe.directory` to avoid "detected dubious ownership" errors on shared/FAT-like filesystems.
- Git subprocesses now use an app-owned global gitconfig (`%LOCALAPPDATA%\\DataGest\\gitconfig`) to avoid permission errors locking `C:\\Users\\...\\.gitconfig`.
- Safe-directory registration now uses canonical `H:/...` style paths and no longer triggers false workspace corruption recovery for dubious-ownership-only errors.
- Git subprocesses now always override pre-existing `GIT_CONFIG_GLOBAL` values to keep app runs isolated from locked user config files.
- Workspace corruption backups now generate unique names even for repeated failures in the same second.
- Registry source normalization now auto-resolves repo-root entries to `registry/registry.json`.
- Removed the redundant History action button from dataset actions (history remains available via the dedicated tab).
- Lock acquisition now removes stale locks only if the lock content is unchanged, reducing stale-lock race risk.
- Workflow cancel no longer raises generic error popups for user-requested cancellations.

## [0.1.1] - 2026-02-18

### Changed
- Workspace initialization now aligns local `main` with `origin/main` when the remote branch exists.
- Server setup now enforces bare repository `HEAD` to `refs/heads/main` for consistent clone behavior.

### Fixed
- Non-fast-forward errors during workspace bootstrap commit are now handled with fetch/rebase/push recovery.
- Repeated `fatal: not in a git directory` failures are mitigated by automatic workspace integrity recovery before workflow execution.
- Project selection and import flows are more resilient when a previously created local workspace is in an inconsistent state.

## [0.1.0] - 2026-02-18

### Added
- Initial desktop PoC built with PySide6.
- Core engine modules for configuration, registry loading, workspace lifecycle, locking, and Git/DVC execution.
- Tool bootstrap flow for first-run Git and DVC setup.
- Dataset workflows for import/publish, fetch latest, history browsing, restore, and return to latest.
- Server bootstrap script to create Git remote, DVC remote, locks, and registry structure.
- PyInstaller build configuration (`onedir`) and CI workflow for lint, test, and packaging.
- Test suite covering core managers and workflows.

### Changed
- Local path Git remotes are normalized to `file:///` URLs for reliable cloning on Windows.
- Application startup prioritizes system Git when available.

### Fixed
- DVC download source resolution with fallback to latest valid Windows binary.
- DVC installer handling to avoid treating installer executables as the CLI binary.
- About dialog no longer triggers unexpected tool installation.
- UI tab color contrast to avoid unreadable white-on-white tab labels.
- Workspace recovery when local project folder exists but is not a valid Git repository.
- Import workflow guard to fail fast if workspace initialization fails.
