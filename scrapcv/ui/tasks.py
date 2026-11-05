"""Ejecución en segundo plano para que la ventana no se congele.

Tkinter no es seguro entre hilos: el trabajo corre en un hilo aparte y se
comunica con la ventana solo mediante una cola que la ventana revisa.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable

from scrapcv.ports import ProgressListener


@dataclass(frozen=True)
class UiEvent:
    kind: str  # info | warning | progress | done | failed
    payload: Any = None


class QueueProgress(ProgressListener):
    """Observer que traduce el progreso del dominio a eventos de la interfaz."""

    def __init__(self, events: "queue.Queue[UiEvent]") -> None:
        self._events = events

    def info(self, message: str) -> None:
        self._events.put(UiEvent("info", message))

    def warning(self, message: str) -> None:
        self._events.put(UiEvent("warning", message))

    def progress(self, done: int, total: int) -> None:
        self._events.put(UiEvent("progress", (done, total)))


@dataclass(frozen=True)
class TaskOutcome:
    name: str
    result: Any = None
    error: BaseException | None = None
    on_success: Callable[[Any], None] | None = None


class BackgroundRunner:
    def __init__(self) -> None:
        self.events: "queue.Queue[UiEvent]" = queue.Queue()
        self.progress = QueueProgress(self.events)
        self._busy = threading.Event()

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def start(self, name: str, work: Callable[[ProgressListener], Any], on_success: Callable[[Any], None] | None = None) -> bool:
        if self._busy.is_set():
            return False
        self._busy.set()

        def target() -> None:
            try:
                result = work(self.progress)
                self.events.put(UiEvent("done", TaskOutcome(name, result, None, on_success)))
            except BaseException as exc:  # se muestra al usuario, no se pierde en el hilo
                self.events.put(UiEvent("failed", TaskOutcome(name, None, exc)))
            finally:
                self._busy.clear()

        threading.Thread(target=target, daemon=True, name=f"scrapcv-{name}").start()
        return True
