from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import CancelCB, DataGestCore, ErrorCB, ProgressCB
from core.config import load_config, save_config
from core.dvc_manager import DVCManager
from core.git_manager import GitManager
from core.lock_manager import LockManager
from core.registry import RegistryLoader
from core.tool_bootstrap import ToolBootstrap
from core.workspace import WorkspaceManager
from models.project import DatasetConfig, DatasetInfo, ProjectConfig
from ui.styles import APP_STYLE
from ui.widgets.dataset_detail import DatasetDetailWidget
from ui.widgets.dataset_list import DatasetListWidget
from ui.widgets.history_panel import HistoryPanel
from ui.widgets.import_dialog import ImportDialog
from ui.widgets.log_viewer import LogViewerDialog
from ui.widgets.options_dialog import OptionsDialog
from ui.widgets.progress_panel import ProgressPanel
from ui.widgets.project_list import ProjectListWidget
from utils.logging_setup import setup_logging
from version import APP_VERSION


logger = logging.getLogger(__name__)


CoreTask = Callable[[ProgressCB, ErrorCB, CancelCB], tuple[bool, str, object | None]]


class CoreTaskRunner(QObject):
    progress = Signal(str, int)
    finished = Signal(bool, str)
    error = Signal(str)
    payload_ready = Signal(object)

    def __init__(self, task: CoreTask) -> None:
        super().__init__()
        self._task = task
        self._cancelled = False

    @Slot()
    def execute(self) -> None:
        success = False
        message = "Task failed."
        try:
            success, message, payload = self._task(self.progress.emit, self.error.emit, self.is_cancelled)
            if payload is not None:
                self.payload_ready.emit(payload)
        except Exception as exc:
            self.error.emit(str(exc))
            message = str(exc)
        self.finished.emit(success, message)

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DataGest")
        self.resize(1280, 820)

        self.config = load_config()
        self._sync_registry_sources_with_config()
        self.log_file = setup_logging(self.config.log_level)

        self.bootstrap = ToolBootstrap(self.config)
        git_exe = shutil.which("git") or self.config.git_executable
        dvc_exe = self.config.dvc_executable

        if not git_exe or not dvc_exe:
            self._bootstrap_tools(need_git=not bool(git_exe), need_dvc=not bool(dvc_exe))
            git_exe = git_exe or str(self.bootstrap.ensure_git())
            dvc_exe = dvc_exe or str(self.bootstrap.ensure_dvc())

        self.git_exe = git_exe
        self.dvc_exe = dvc_exe
        self._reset_workspace_services()
        self.lock_manager = LockManager(
            Path(self.config.locks_path),
            ttl_hours=self.config.lock_ttl_hours,
            admin_mode=self.config.admin_mode,
        )
        self.core_api = DataGestCore(self.workspace, self.lock_manager)
        self.registry_loader = RegistryLoader(self.config.registry_path)

        self.current_project: ProjectConfig | None = None
        self.current_dataset_info: DatasetInfo | None = None

        self._workflow_thread: QThread | None = None
        self._workflow: CoreTaskRunner | None = None
        self._updating_registry_selector = False

        self.project_list = ProjectListWidget()
        self.dataset_list = DatasetListWidget()
        self.detail = DatasetDetailWidget()
        self.history = HistoryPanel()
        self.progress = ProgressPanel()

        self._build_ui()
        self._wire_events()
        self._populate_registry_selector()
        self.load_registry()

    def _build_ui(self) -> None:
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.project_list)
        left_layout.addWidget(self.dataset_list)

        right_tabs = QTabWidget()
        right_tabs.addTab(self.detail, "Dataset")
        right_tabs.addTab(self.history, "History")
        self.right_tabs = right_tabs

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right_tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)

        central = QWidget()
        layout = QVBoxLayout(central)
        top_actions = QHBoxLayout()

        self.registry_selector = QComboBox()
        self.registry_selector.setMinimumWidth(420)
        self.registry_selector.setToolTip("Selected registry source")

        reload_btn = QPushButton("Reload Registry")
        reload_btn.clicked.connect(self.load_registry)
        logs_btn = QPushButton("Logs")
        logs_btn.clicked.connect(self.show_logs)
        options_btn = QPushButton("Options")
        options_btn.clicked.connect(self.show_options)
        about_btn = QPushButton("About")
        about_btn.clicked.connect(self.show_about)

        top_actions.addWidget(self.registry_selector)
        top_actions.addWidget(reload_btn)
        top_actions.addWidget(logs_btn)
        top_actions.addWidget(options_btn)
        top_actions.addWidget(about_btn)
        top_actions.addStretch()

        layout.addLayout(top_actions)
        layout.addWidget(splitter)
        layout.addWidget(self.progress)

        self.setCentralWidget(central)

    def _wire_events(self) -> None:
        self.registry_selector.currentIndexChanged.connect(self.on_registry_source_changed)
        self.project_list.project_selected.connect(self.on_project_selected)
        self.dataset_list.dataset_selected.connect(self.on_dataset_selected)
        self.right_tabs.currentChanged.connect(self.on_tab_changed)

        self.detail.import_requested.connect(self.on_import_requested)
        self.detail.publish_requested.connect(self.on_publish_requested)
        self.detail.fetch_requested.connect(self.on_fetch_requested)
        self.detail.restore_latest_requested.connect(self.on_return_to_latest_requested)

        self.history.restore_requested.connect(self.on_restore_requested)
        self.history.latest_requested.connect(self.on_return_to_latest_requested)

        self.progress.cancel_requested.connect(self.on_cancel_requested)

    def _sync_registry_sources_with_config(self) -> None:
        normalized: list[str] = []
        for item in [self.config.registry_path, *self.config.registry_sources]:
            text = str(item).strip()
            if text and text not in normalized:
                normalized.append(text)

        changed = False
        if normalized != self.config.registry_sources:
            self.config.registry_sources = normalized
            changed = True

        if self.config.registry_path not in self.config.registry_sources and self.config.registry_sources:
            self.config.registry_path = self.config.registry_sources[0]
            changed = True

        if changed:
            save_config(self.config)

    def _populate_registry_selector(self) -> None:
        self._updating_registry_selector = True
        self.registry_selector.clear()

        for source in self.config.registry_sources:
            self.registry_selector.addItem(source, source)

        index = self.registry_selector.findData(self.config.registry_path)
        if index >= 0:
            self.registry_selector.setCurrentIndex(index)

        self._updating_registry_selector = False

    def _bootstrap_tools(self, need_git: bool = True, need_dvc: bool = True) -> None:
        dialog = QProgressDialog("Downloading tools...", "", 0, 100, self)
        dialog.setWindowTitle("First run setup")
        dialog.setCancelButton(None)
        dialog.setAutoClose(True)

        def update(message: str, percent: int) -> None:
            dialog.setLabelText(message)
            dialog.setValue(percent)
            QApplication.processEvents()

        dialog.show()
        try:
            if need_git:
                self.bootstrap.ensure_git(progress_cb=update)
            if need_dvc:
                self.bootstrap.ensure_dvc(progress_cb=update)
        except Exception as exc:
            QMessageBox.critical(self, "Tool setup failed", str(exc))
            raise
        finally:
            dialog.close()

    def load_registry(self) -> None:
        try:
            self.registry_loader = RegistryLoader(self.config.registry_path)
            projects = self.registry_loader.load()
            self.project_list.set_projects(projects)
            self.statusBar().showMessage(
                f"Loaded {len(projects)} project(s) from {self.config.registry_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Registry error", str(exc))
            self.statusBar().showMessage("Registry load failed")

    def on_registry_source_changed(self, index: int) -> None:
        if self._updating_registry_selector or index < 0:
            return

        selected = self.registry_selector.itemData(index)
        if not selected:
            return
        selected_path = str(selected)
        if selected_path == self.config.registry_path:
            return

        self.config.registry_path = selected_path
        self._sync_registry_sources_with_config()
        self.load_registry()

    def on_project_selected(self, project: ProjectConfig) -> None:
        self.current_project = project
        self.current_dataset_info = None

        datasets: list[DatasetInfo]
        try:
            self.workspace.init_workspace(project)
            datasets = self.workspace.list_datasets()
            if not datasets:
                datasets = [self._dataset_info_from_config(ds) for ds in project.datasets]
        except Exception as exc:
            logger.warning("Workspace init failed on project selection: %s", exc)
            datasets = [self._dataset_info_from_config(ds) for ds in project.datasets]

        self.dataset_list.set_datasets(datasets)

    def _dataset_info_from_config(self, ds: DatasetConfig) -> DatasetInfo:
        return DatasetInfo(
            config=ds,
            file_count=0,
            total_size_bytes=0,
            last_updated=None,
            last_author=None,
            is_locked=False,
            locked_by=None,
            local_state="not_downloaded",
        )

    def on_dataset_selected(self, dataset_info: DatasetInfo) -> None:
        self.current_dataset_info = dataset_info
        if not self.current_project:
            return
        path = self.workspace.root_path / self.current_project.project_id / "datasets" / dataset_info.config.dataset_id
        self.detail.set_dataset(dataset_info, path)
        self.on_history_requested(activate_tab=False)

    def on_import_requested(self) -> None:
        if not self.current_project or not self.current_dataset_info:
            QMessageBox.warning(self, "No dataset", "Select a dataset first.")
            return

        dialog = ImportDialog(self.current_dataset_info.config.name, self)
        if dialog.exec() != ImportDialog.Accepted:
            return

        source, description, replace_dataset = dialog.get_values()

        project = self.current_project
        dataset = self.current_dataset_info.config

        def task(progress_cb: ProgressCB, error_cb: ErrorCB, cancel_cb: CancelCB) -> tuple[bool, str, object | None]:
            success, message = self.core_api.import_dataset(
                project=project,
                dataset=dataset,
                source_folder=source,
                description=description,
                replace_dataset=replace_dataset,
                progress_cb=progress_cb,
                error_cb=error_cb,
                cancel_cb=cancel_cb,
            )
            return success, message, None

        self._run_workflow(task, refresh_after=True)

    def on_publish_requested(self) -> None:
        if not self.current_project or not self.current_dataset_info:
            QMessageBox.warning(self, "No dataset", "Select a dataset first.")
            return

        dataset_name = self.current_dataset_info.config.name
        default_message = f"Update dataset: {dataset_name}"
        message, ok = QInputDialog.getText(
            self,
            "Commit & Push",
            "Commit message",
            text=default_message,
        )
        if not ok or not message.strip():
            return

        project = self.current_project
        dataset_id = self.current_dataset_info.config.dataset_id
        commit_message = message.strip()

        def task(progress_cb: ProgressCB, error_cb: ErrorCB, cancel_cb: CancelCB) -> tuple[bool, str, object | None]:
            success, result_message = self.core_api.publish(
                project=project,
                commit_message=commit_message,
                dataset_id=dataset_id,
                progress_cb=progress_cb,
                error_cb=error_cb,
                cancel_cb=cancel_cb,
            )
            return success, result_message, None

        self._run_workflow(task, refresh_after=True)

    def on_fetch_requested(self) -> None:
        if not self.current_project:
            return

        project = self.current_project

        def task(progress_cb: ProgressCB, error_cb: ErrorCB, cancel_cb: CancelCB) -> tuple[bool, str, object | None]:
            success, message = self.core_api.fetch(
                project=project,
                progress_cb=progress_cb,
                error_cb=error_cb,
                cancel_cb=cancel_cb,
            )
            return success, message, None

        self._run_workflow(task, refresh_after=True)

    def on_history_requested(self, activate_tab: bool = True) -> None:
        if not self.current_project or not self.current_dataset_info:
            return
        if self._workflow_thread is not None:
            return

        project = self.current_project
        dataset_id = self.current_dataset_info.config.dataset_id

        def task(progress_cb: ProgressCB, error_cb: ErrorCB, cancel_cb: CancelCB) -> tuple[bool, str, object | None]:
            success, message, commits = self.core_api.load_history(
                project=project,
                dataset_id=dataset_id,
                progress_cb=progress_cb,
                error_cb=error_cb,
                cancel_cb=cancel_cb,
            )
            payload: object | None = commits if success else None
            return success, message, payload

        if activate_tab:
            self.right_tabs.setCurrentWidget(self.history)
        self._run_workflow(task, refresh_after=False, payload_handler=self.history.set_commits)

    def on_tab_changed(self, index: int) -> None:
        if self.right_tabs.widget(index) is self.history:
            self.on_history_requested(activate_tab=False)

    def on_restore_requested(self, commit_hash: str) -> None:
        if not self.current_project:
            return

        short_hash = commit_hash[:8]
        choice = QMessageBox.question(
            self,
            "Confirm restore",
            (
                f"Restore dataset to commit {short_hash}?\n\n"
                "This will replace local files with a historical version in your workspace."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if choice != QMessageBox.Yes:
            return

        project = self.current_project

        def task(progress_cb: ProgressCB, error_cb: ErrorCB, cancel_cb: CancelCB) -> tuple[bool, str, object | None]:
            success, message = self.core_api.restore(
                project=project,
                commit_ref=commit_hash,
                progress_cb=progress_cb,
                error_cb=error_cb,
                cancel_cb=cancel_cb,
            )
            return success, message, None

        self._run_workflow(task, refresh_after=True)

    def on_return_to_latest_requested(self) -> None:
        if not self.current_project:
            return
        project = self.current_project

        def task(progress_cb: ProgressCB, error_cb: ErrorCB, cancel_cb: CancelCB) -> tuple[bool, str, object | None]:
            success, message = self.core_api.return_to_latest(
                project=project,
                progress_cb=progress_cb,
                error_cb=error_cb,
                cancel_cb=cancel_cb,
            )
            return success, message, None

        self._run_workflow(task, refresh_after=True)

    def on_cancel_requested(self) -> None:
        if self._workflow is not None:
            self._workflow.cancel()
            self.progress.append_log("Cancel requested (best effort)")

    @Slot(str, int)
    def _on_workflow_progress(self, message: str, percent: int) -> None:
        self.progress.update_progress(message, percent)

    @Slot(str)
    def _on_workflow_error(self, message: str) -> None:
        QMessageBox.critical(self, "Workflow error", message)

    def _run_workflow(
        self,
        task: CoreTask,
        refresh_after: bool,
        payload_handler: Callable[[object], None] | None = None,
    ) -> None:
        if self._workflow_thread is not None:
            QMessageBox.warning(self, "Busy", "Another task is already running.")
            return

        self.progress.clear()
        self.progress.set_running(True)

        thread = QThread(self)
        workflow = CoreTaskRunner(task)
        workflow.moveToThread(thread)

        workflow.progress.connect(self._on_workflow_progress, Qt.ConnectionType.QueuedConnection)
        workflow.error.connect(self._on_workflow_error, Qt.ConnectionType.QueuedConnection)
        if payload_handler is not None:
            workflow.payload_ready.connect(payload_handler, Qt.ConnectionType.QueuedConnection)

        def on_finished(success: bool, message: str) -> None:
            self.progress.set_finished(success, message)
            self.statusBar().showMessage(message)
            thread.quit()
            if refresh_after and self.current_project:
                self.on_project_selected(self.current_project)

        workflow.finished.connect(on_finished, Qt.ConnectionType.QueuedConnection)

        thread.started.connect(workflow.execute)
        thread.finished.connect(workflow.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_running_workflow)

        self._workflow_thread = thread
        self._workflow = workflow
        thread.start()

    def _clear_running_workflow(self) -> None:
        self._workflow_thread = None
        self._workflow = None

    def closeEvent(self, event: QCloseEvent) -> None:
        thread = self._workflow_thread
        if thread is not None and thread.isRunning():
            choice = QMessageBox.question(
                self,
                "Task running",
                (
                    "A background task is still running.\n"
                    "Cancel it and wait for shutdown?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                event.ignore()
                return

            if self._workflow is not None:
                self._workflow.cancel()
                self.progress.append_log("Close requested: waiting for workflow to stop...")

            thread.quit()
            if not thread.wait(5000):
                QMessageBox.warning(
                    self,
                    "Still running",
                    "The current task did not stop yet. Please wait and try again.",
                )
                event.ignore()
                return

        super().closeEvent(event)

    def show_logs(self) -> None:
        dialog = LogViewerDialog(self.log_file, self)
        dialog.exec()

    def _reset_workspace_services(self) -> None:
        root = Path(self.config.workspace_root)
        self.git_manager = GitManager(
            root,
            git_executable=self.git_exe,
            timeout_seconds=self.config.git_timeout_seconds,
        )
        self.dvc_manager = DVCManager(
            root,
            dvc_executable=self.dvc_exe,
            timeout_seconds=self.config.dvc_timeout_seconds,
        )
        self.workspace = WorkspaceManager(root, self.git_manager, self.dvc_manager)
        if hasattr(self, "lock_manager"):
            self.core_api = DataGestCore(self.workspace, self.lock_manager)

    def show_options(self) -> None:
        if self._workflow_thread is not None:
            QMessageBox.warning(self, "Busy", "Wait for the current task to finish.")
            return

        dialog = OptionsDialog(self.config.workspace_root, self.config.registry_sources, self)
        if dialog.exec() != OptionsDialog.Accepted:
            return

        new_root = dialog.workspace_root
        new_registry_sources = dialog.registry_sources

        workspace_changed = new_root != self.config.workspace_root
        sources_changed = new_registry_sources != self.config.registry_sources
        if not workspace_changed and not sources_changed:
            return
        if not new_registry_sources:
            QMessageBox.warning(self, "Invalid sources", "At least one registry source is required.")
            return

        self.config.workspace_root = new_root
        self.config.registry_sources = new_registry_sources
        if self.config.registry_path not in self.config.registry_sources:
            if not self.config.registry_sources:
                QMessageBox.warning(self, "Invalid sources", "At least one registry source is required.")
                return
            self.config.registry_path = self.config.registry_sources[0]
        self._sync_registry_sources_with_config()
        save_config(self.config)

        if workspace_changed:
            self._reset_workspace_services()

        self._populate_registry_selector()
        self.load_registry()

        if workspace_changed and self.current_project:
            self.on_project_selected(self.current_project)

        self.statusBar().showMessage("Options updated.")

    def show_about(self) -> None:
        versions = self.bootstrap.check_versions(install_missing=False)
        QMessageBox.information(
            self,
            "About DataGest",
            (
                f"DataGest v{APP_VERSION}\n"
                f"Git: {versions.get('git', 'unknown')}\n"
                f"DVC: {versions.get('dvc', 'unknown')}\n"
                f"Workspace root: {self.config.workspace_root}"
            ),
        )


def run_app() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
