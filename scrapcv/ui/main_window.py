"""Ventana principal: arma las pestañas y reparte los eventos del hilo de trabajo."""
from __future__ import annotations

import queue
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any, Callable

from scrapcv.infrastructure.logging_setup import REDACTOR
from scrapcv.ports import ProgressListener
from scrapcv.ui.controller import AppController
from scrapcv.ui.cv_view import CvView
from scrapcv.ui.evidence_view import EvidenceView
from scrapcv.ui.settings_view import SettingsView
from scrapcv.ui.tasks import BackgroundRunner, TaskOutcome
from scrapcv.ui.widgets import MONO, apply_style, scrolled_text

POLL_MS = 100


class MainWindow:
    def __init__(self, root: tk.Tk, controller: AppController, runner: BackgroundRunner | None = None) -> None:
        self._root = root
        self._controller = controller
        self._runner = runner or BackgroundRunner()
        root.title("ScrapCV · De Canvas a Currículum")
        root.geometry("1180x800")
        root.minsize(980, 640)
        apply_style(root)
        self._build()
        root.after(POLL_MS, self._poll)
        root.after(50, self._refresh_views)

    def _build(self) -> None:
        root = self._root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, padding=(16, 12, 16, 0))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="ScrapCV", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="  Un CV construido con la evidencia de tus entregas", style="Muted.TLabel").pack(side="left", pady=(6, 0))

        body = ttk.PanedWindow(root, orient="vertical")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self._tabs = ttk.Notebook(body)
        self._settings = SettingsView(self._tabs, self._controller, self.start, self._on_settings_applied)
        self._evidence = EvidenceView(self._tabs, self._controller, self.start)
        self._cv = CvView(self._tabs, self._controller, self.start)
        self._tabs.add(self._settings, text="  Configuración  ")
        self._tabs.add(self._evidence, text="  Evidencia  ")
        self._tabs.add(self._cv, text="  Currículum  ")
        self._tabs.bind("<<NotebookTabChanged>>", lambda _e: self._refresh_views())

        console = ttk.Frame(body, padding=(8, 4))
        console.columnconfigure(0, weight=1)
        console.rowconfigure(1, weight=1)
        status_row = ttk.Frame(console)
        status_row.grid(row=0, column=0, sticky="ew")
        self._task_label = ttk.Label(status_row, text="Listo.", style="Muted.TLabel")
        self._task_label.pack(side="left")
        self._bar = ttk.Progressbar(status_row, length=260, mode="determinate")
        self._bar.pack(side="right")
        frame, self._log = scrolled_text(console, height=7, font=MONO)
        frame.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self._log.tag_configure("warning", foreground="#a5520f")
        self._log.tag_configure("error", foreground="#b42318")
        self._log.tag_configure("ok", foreground="#1e7b34")
        self._log.configure(state="disabled")

        body.add(self._tabs, weight=5)
        body.add(console, weight=1)

    # --- Tareas en segundo plano ------------------------------------------------------------
    def start(self, name: str, work: Callable[[ProgressListener], Any], on_success: Callable[[Any], None] | None = None) -> None:
        if not self._runner.start(name, work, on_success):
            self._write(f"Espera a que termine la tarea en curso antes de iniciar «{name}».", "warning")
            return
        self._task_label.configure(text=f"Trabajando: {name}…")
        self._bar.configure(mode="indeterminate")
        self._bar.start(12)

    def _poll(self) -> None:
        try:
            while True:
                event = self._runner.events.get_nowait()
                if event.kind == "info":
                    self._write(event.payload)
                elif event.kind == "warning":
                    self._write(event.payload, "warning")
                elif event.kind == "progress":
                    done, total = event.payload
                    self._bar.stop()
                    self._bar.configure(mode="determinate", maximum=max(1, total), value=done)
                elif event.kind in ("done", "failed"):
                    self._finish(event.payload)
        except queue.Empty:
            pass
        self._root.after(POLL_MS, self._poll)

    def _finish(self, outcome: TaskOutcome) -> None:
        self._bar.stop()
        self._bar.configure(mode="determinate", value=0)
        if outcome.error is None:
            self._task_label.configure(text=f"Terminado: {outcome.name}.")
            self._write(f"✔ {outcome.name} terminado.", "ok")
            if outcome.on_success:
                outcome.on_success(outcome.result)
            self._refresh_views()
        else:
            message = REDACTOR.redact(str(outcome.error) or outcome.error.__class__.__name__)
            self._task_label.configure(text=f"Error en {outcome.name}.")
            self._write(f"✖ {outcome.name}: {message}", "error")
            messagebox.showerror("ScrapCV", f"{outcome.name}: {message}")

    def _write(self, message: str, tag: str | None = None) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", f"{datetime.now():%H:%M:%S}  {REDACTOR.redact(message)}\n", tag or ())
        self._log.see("end")
        self._log.configure(state="disabled")

    # --- Coordinación de vistas ---------------------------------------------------------------
    def _on_settings_applied(self) -> None:
        self._refresh_views()
        self._tabs.select(self._evidence)

    def _refresh_views(self) -> None:
        if self._runner.busy:  # el índice se está escribiendo en otro hilo
            return
        try:
            self._evidence.refresh()
            self._cv.refresh()
        except Exception as exc:  # p. ej. falta el token con Canvas real
            self._task_label.configure(text=str(exc))
