# DataGest Roadmap (from 2026-02-18 audit)

This roadmap converts the full audit into an execution plan, ordered by priority.

All planned items in this roadmap are now completed.

## Execution Status

| Item | Title | Priority | Status |
|---|---|---|---|
| 1 | Fix lock stale/reacquire race | P0 | Completed |
| 2 | Implement real workflow cancellation | P0 | Completed |
| 3 | Add restore confirmation barrier | P0 | Completed |
| 4 | Harden cross-thread UI signaling | P1 | Completed |
| 5 | Add subprocess timeout policy | P1 | Completed |
| 6 | Add network retry/backoff for UNC operations | P1 | Completed |
| 7 | Guard shutdown while worker thread is active | P1 | Completed |
| 8 | Remove silent exception masking in workspace status | P1 | Completed |
| 9 | Defensive config update for registry sources | P1 | Completed |
| 10 | Add missing workflow tests for destructive paths | P1 | Completed |
| 11 | Single source of truth for app version | P2 | Completed |
| 12 | Refactor duplicated global gitconfig logic | P2 | Completed |
| 13 | Clarify/upgrade `validate_unc_path()` contract | P2 | Completed |
| 14 | Decide cache behavior in `RegistryLoader` | P2 | Completed |
| 15 | Protocol-based interfaces for managers | P2 | Completed |
| 16 | Improve test structure with shared fixtures | P2 | Completed |
| 17 | Packaging/CI cleanup | P2 | Completed |
| 18 | Remove unused import in `project_list.py` | P3 | Completed |
| 19 | Use or remove `DATASET_YAML_REQUIRED_KEYS` | P3 | Completed |
| 20 | Type style consistency (`Optional` usage) | P3 | Completed |

## Decision Summary (For/Against)

| ID | Audit item | Decision | Why |
|---|---|---|---|
| C1 | Lock race in `LockManager.acquire()` | For | Valid concurrency risk around stale lock removal and re-acquire window. |
| C2 | Cancel button ineffective | For | `_cancelled` is set but never checked by workflows. |
| C3 | Cross-thread UI signal safety | Partially for | Qt AutoConnection often works, but explicit queued handling is safer and clearer. |
| M4 | `registry_sources[0]` potential crash | For | UI guards exist but core save path should still be defensive. |
| M5 | Silent exception swallow in `_dvc_dirty_datasets()` | For | Needs logging for observability. |
| M6 | Version hardcoded in multiple files | For | Must have a single source of truth. |
| M7 | `validate_unc_path()` weak semantics | For | Function name implies UNC validation, implementation only checks existence. |
| M8 | `_app_global_gitconfig` duplicated | For | Standard DRY refactor. |
| m9 | Unused import in `project_list.py` | For | Cleanup. |
| m10 | `DATASET_YAML_REQUIRED_KEYS` unused | For | Either use it or remove it. |
| m11 | `RegistryLoader._cached` never read | For | Dead field or missing cache behavior. |
| m12 | `Optional[X]` style inconsistency | Against (low value) | Style-only; keep as very low priority. |
| A1 | Add Protocol for Git/DVC managers | For | Improves testability and boundaries. |
| A2 | Log caught errors instead of silent ignore | For | Improves diagnostics in factory environments. |
| A3 | Add `conftest.py` and shared test fixtures | For | Reduces test duplication. |
| A4 | Add subprocess timeouts | For | Important against network hangs. |
| A5 | Add retry/backoff for UNC network ops | For | High value in unstable SMB networks. |
| A6 | Protect app close with running workflow | For | Avoid orphan thread and undefined shutdown. |
| A7 | Confirmation before restore | For | Prevent accidental destructive checkout. |
| A8 | Add tests for missing destructive workflows | For | `FetchLatest`, `RestoreVersion`, `ReturnToLatest` should be covered. |
| A9 | Add UI tests | Partially for | Useful but lower priority than core reliability. |
| A10 | Packaging/CI cleanup (`ruff`, dependency source, dist hygiene) | For | Improves release quality and maintainability. |

## P0 (Immediate reliability and data safety)

### 1) Fix lock stale/reacquire race (`C1`)
Owner: Core  
Status: Completed

Tasks:
- Make stale lock cleanup compare expected stale metadata before delete.
- Prevent deleting a freshly recreated lock from another client.
- Add stress test with two concurrent acquire attempts.

Acceptance criteria:
- Under concurrent stale lock contention, only one client can acquire.
- No client can delete another client fresh lock via stale path.

### 2) Implement real workflow cancellation (`C2`)
Owner: Workflows/UI  
Status: Completed

Tasks:
- Add `_check_cancelled()` guard in `BaseWorkflow`.
- Check cancellation between every heavy step in all workflows.
- Return clean "Cancelled by user" state.

Acceptance criteria:
- Cancel stops long operations before commit/push side effects.
- UI and logs clearly show cancelled state.

### 3) Add restore confirmation barrier (`A7`)
Owner: UI  
Status: Completed

Tasks:
- Show confirmation dialog before running `RestoreVersionWorkflow`.
- Include warning that workspace will move to historical state.

Acceptance criteria:
- Restore never starts without explicit user confirmation.

## P1 (Robustness and operational hardening)

### 4) Harden cross-thread UI signaling (`C3`)
Owner: UI  
Status: Completed

Tasks:
- Replace inline lambda error handler with dedicated Qt slot.
- Use explicit queued connection where receiver updates GUI.

Acceptance criteria:
- No direct GUI mutation from worker thread code paths.

### 5) Add subprocess timeout policy (`A4`)
Owner: Core  
Status: Completed

Tasks:
- Add configurable timeout for Git/DVC run/popen wrappers.
- Surface timeout errors with actionable message.

Acceptance criteria:
- Hung network operations terminate and report timeout.

### 6) Add network retry/backoff for UNC operations (`A5`)
Owner: Core  
Status: Completed

Tasks:
- Retry transient Git/DVC pull/push failures (bounded attempts).
- Add exponential backoff and retryable error matching.

Acceptance criteria:
- Transient SMB errors recover automatically in common cases.

### 7) Guard shutdown while worker thread is active (`A6`)
Owner: UI  
Status: Completed

Tasks:
- Implement `closeEvent` to block or request cancel when workflow active.
- Ensure graceful thread stop before window closes.

Acceptance criteria:
- No orphan workflow thread on app exit.

### 8) Remove silent exception masking in workspace status (`M5`, `A2`)
Owner: Core  
Status: Completed

Tasks:
- Log warning/error context in `_dvc_dirty_datasets()` and similar catches.

Acceptance criteria:
- Failing DVC status is visible in logs and diagnosable.

### 9) Defensive config update for registry sources (`M4`)
Owner: UI/Core  
Status: Completed

Tasks:
- Add non-empty guard before indexing `[0]` in options apply path.
- Keep fallback behavior if sources unexpectedly empty.

Acceptance criteria:
- No `IndexError` path during options save.

### 10) Add missing workflow tests for destructive paths (`A8`)
Owner: Tests  
Status: Completed

Tasks:
- Add tests for `FetchLatestWorkflow`, `RestoreVersionWorkflow`, `ReturnToLatestWorkflow`.
- Cover dirty workspace, detached head, checkout failure scenarios.

Acceptance criteria:
- All destructive workflows have happy and failure path tests.

## P2 (Maintainability and consistency)

### 11) Single source of truth for app version (`M6`)
Owner: Core/UI  
Status: Completed

Tasks:
- Centralize version in `src/__init__.py` or `importlib.metadata`.
- Replace hardcoded literals in About dialog and lock metadata defaults.

Acceptance criteria:
- Version bump requires one change only.

### 12) Refactor duplicated global gitconfig logic (`M8`)
Owner: Core  
Status: Completed

Tasks:
- Move helper to shared utility module.
- Reuse from both Git and DVC managers.

Acceptance criteria:
- No duplicate implementation of app gitconfig path logic.

### 13) Clarify/upgrade `validate_unc_path()` contract (`M7`)
Owner: Utils  
Status: Completed

Tasks:
- Either rename to `path_exists()` or implement true UNC syntax + accessibility validation.

Acceptance criteria:
- Function behavior matches its name and documentation.

### 14) Decide cache behavior in `RegistryLoader` (`m11`)
Owner: Core  
Status: Completed

Tasks:
- Either use `_cached` for repeated reads or remove it.

Acceptance criteria:
- No dead cache field.

### 15) Protocol-based interfaces for managers (`A1`)
Owner: Core/Tests  
Status: Completed

Tasks:
- Define Protocols for Git/DVC operations consumed by workflows/workspace.
- Type tests and fakes against protocols.

Acceptance criteria:
- Test doubles follow explicit interfaces, reducing drift.

### 16) Improve test structure with shared fixtures (`A3`)
Owner: Tests  
Status: Completed

Tasks:
- Add `tests/conftest.py` for common fake managers and fixtures.

Acceptance criteria:
- Reduced duplication in test setup code.

### 17) Packaging/CI cleanup (`A10`)
Owner: DevOps  
Status: Completed

Tasks:
- Add/align `ruff` config and enforce in CI.
- Clean artifacts policy (`dist/`, `build/`) and release packaging consistency.
- Decide single dependency source (`pyproject` vs duplicated `requirements.txt`).

Acceptance criteria:
- Reproducible CI checks and clean release process.

## P3 (Low-priority cleanup)

### 18) Remove unused import in `project_list.py` (`m9`)
Owner: UI  
Status: Completed

### 19) Use or remove `DATASET_YAML_REQUIRED_KEYS` (`m10`)
Owner: Models/Core  
Status: Completed

### 20) Type style consistency (`m12`)
Owner: Core  
Status: Completed

Notes:
- Keep very low priority.
- Apply only when touching nearby files for functional work.

## Suggested execution order

1. P0 items 1-3  
2. P1 items 4-10  
3. P2 items 11-17  
4. P3 items 18-20
