from __future__ import annotations

import time
from typing import Callable


class _BoundSignal:
    def __init__(self) -> None:
        self._callbacks: list[Callable] = []

    def connect(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs) -> None:
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class Signal:  # type: ignore[misc]
    def __init__(self, *args, **kwargs) -> None:
        self.name: str | None = None

    def __set_name__(self, owner, name) -> None:
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        store = instance.__dict__.setdefault("_signals", {})
        assert self.name is not None
        if self.name not in store:
            store[self.name] = _BoundSignal()
        return store[self.name]


class QObject:  # type: ignore[misc]
    def __init__(self) -> None:
        pass


class BaseWorkflow(QObject):
    progress = Signal(str, int)
    finished = Signal(bool, str)
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._cancelled = False

    def execute(self) -> None:
        raise NotImplementedError

    def cancel(self) -> None:
        self._cancelled = True

    def _check_cancelled(self) -> None:
        if self._cancelled:
            raise WorkflowCancelled("Cancelled by user.")

    def _emit_progress(self, message: str, percent: int) -> None:
        self._check_cancelled()
        self.progress.emit(message, max(0, min(100, percent)))

    def _emit_finished(self, success: bool, message: str) -> None:
        self.finished.emit(success, message)

    def _emit_error(self, message: str) -> None:
        self.error.emit(message)

    def _is_retryable_network_error(self, message: str) -> bool:
        lowered = message.lower()
        markers = (
            "network",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "could not resolve host",
            "unable to access",
            "transport endpoint",
            "broken pipe",
            "resource busy",
            "name or service not known",
        )
        return any(marker in lowered for marker in markers)

    def _run_network_op_with_retry(
        self,
        operation: Callable[[], None],
        label: str,
        retries: int = 3,
    ) -> None:
        attempts = max(retries, 1)
        for attempt in range(1, attempts + 1):
            self._check_cancelled()
            try:
                operation()
                return
            except WorkflowCancelled:
                raise
            except Exception as exc:
                is_last = attempt >= attempts
                retryable = self._is_retryable_network_error(str(exc))
                if is_last or not retryable:
                    raise

                delay = min(8.0, 0.75 * (2 ** (attempt - 1)))
                first_line = str(exc).splitlines()[0] if str(exc).strip() else "network error"
                self._emit_progress(
                    f"{label} failed ({first_line}). Retrying in {delay:.1f}s (attempt {attempt + 1}/{attempts})",
                    0,
                )
                time.sleep(delay)


class WorkflowCancelled(RuntimeError):
    pass
