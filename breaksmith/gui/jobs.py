from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class JobSignals(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str, str)
    canceled = Signal(str)


@dataclass(slots=True)
class CancelToken:
    canceled: bool = False

    def cancel(self) -> None:
        self.canceled = True


class FunctionJob(QRunnable):
    def __init__(self, function: Callable[..., Any], *, token: CancelToken | None = None) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.function = function
        self.token = token or CancelToken()
        self.signals = JobSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(self.signals.progress.emit, lambda: self.token.canceled)
        except InterruptedError as exc:
            self.signals.canceled.emit(str(exc) or "Operation canceled")
        except Exception as exc:  # pragma: no cover - UI reports the formatted traceback.
            self.signals.failed.emit(str(exc), traceback.format_exc())
        else:
            self.signals.finished.emit(result)
