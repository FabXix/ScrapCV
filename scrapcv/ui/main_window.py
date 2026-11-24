"""Ventana principal: barra lateral con los tres pasos, pantallas y progreso amable.

Lo técnico (qué archivo se descarga, cuántas líneas tiene) va a un registro que solo se abre si el usuario
lo pide; en pantalla solo se ve una tarjeta flotante con lo importante («Leyendo tus entregas… 12 de 40»).
"""
from __future__ import annotations

import logging
import queue
import tkinter as tk
from dataclasses import replace
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any, Callable

from scrapcv.infrastructure.logging_setup import REDACTOR
from scrapcv.ports import ProgressListener
from scrapcv.ui.controller import AppController
from scrapcv.ui.cv_view import CvView
from scrapcv.ui.evidence_view import EvidenceView
from scrapcv.ui.messages import friendly_error
from scrapcv.ui.settings_view import SettingsView
from scrapcv.ui.tasks import BackgroundRunner, TaskOutcome
from scrapcv.ui.welcome_view import WelcomeView
from scrapcv.ui.widgets import ACCENT, BG, MONO, ProgressToast, apply_style, scrolled_text

POLL_MS = 100
log = logging.getLogger("scrapcv.ui")

SIDEBAR = "#101a33"
SIDEBAR_HOVER = "#18244a"
SIDEBAR_ACTIVE = "#1f2d5c"
SIDE_TEXT = "#e8edf8"
SIDE_MUTED = "#8b97b5"
_HEADLINES = ("Paso", "Leyendo", "Redactando", "Eligiendo", "Comparando", "Agrupando", "Conectando", "Consultando",
              "Preparando")
_TASK_TITLES = {
    "Conectar": "Conectando con Canvas…",
    "Traer entregas": "Trayendo tus entregas…",
    "Generar CV": "Armando tu CV…",
    "Cambio de CV": "Aplicando tu cambio…",
    "Ejemplo": "Preparando el ejemplo…",
}


class NavItem(tk.Frame):
    """Paso de la barra lateral: círculo con número (o ✔), título y subtítulo."""

    def __init__(self, parent: tk.Widget, number: str, title: str, subtitle: str, command: Callable[[], None]) -> None:
        super().__init__(parent, background=SIDEBAR, cursor="hand2", padx=14, pady=10)
        self._number, self._active, self._done = number, False, False
        self._bar = tk.Frame(self, background=SIDEBAR, width=3)
        self._bar.pack(side="left", fill="y", padx=(0, 12))
        self._badge = tk.Label(self, text=number, width=3, font=("Segoe UI Semibold", 10))
        self._badge.pack(side="left", anchor="n", pady=(2, 0))
        text = tk.Frame(self, background=SIDEBAR)
        text.pack(side="left", fill="x", padx=(12, 0))
        self._title = tk.Label(text, text=title, background=SIDEBAR, foreground=SIDE_TEXT, font=("Segoe UI Semibold", 11),
                               anchor="w")
        self._title.pack(anchor="w")
        scale = max(1.0, parent.winfo_fpixels("1i") / 96)
        self._sub = tk.Label(text, text=subtitle, background=SIDEBAR, foreground=SIDE_MUTED, font=("Segoe UI", 9),
                             anchor="w", justify="left", wraplength=int(165 * scale))
        self._sub.pack(anchor="w")
        self._parts = (self, text, self._title, self._sub)
        for widget in (self, text, self._title, self._sub, self._badge, self._bar):
            widget.bind("<Button-1>", lambda _e: command())
            widget.bind("<Enter>", lambda _e: self._paint(hover=True))
            widget.bind("<Leave>", lambda _e: self._paint())
        self._paint()

    def set_state(self, active: bool | None = None, done: bool | None = None) -> None:
        if active is not None:
            self._active = active
        if done is not None:
            self._done = done
        self._paint()

    def _paint(self, hover: bool = False) -> None:
        bg = SIDEBAR_ACTIVE if self._active else (SIDEBAR_HOVER if hover else SIDEBAR)
        for widget in self._parts:
            widget.configure(background=bg)
        self._bar.configure(background=ACCENT if self._active else bg)
        if self._done:
            self._badge.configure(text="✔", background="#12805c", foreground="#ffffff")
        elif self._active:
            self._badge.configure(text=self._number, background=ACCENT, foreground="#ffffff")
        else:
            self._badge.configure(text=self._number, background="#2a3762", foreground=SIDE_TEXT)


class MainWindow:
    def __init__(self, root: tk.Tk, controller: AppController, runner: BackgroundRunner | None = None) -> None:
        self._root = root
        self._controller = controller
        self._runner = runner or BackgroundRunner()
        self._connected = False
        self._log_lines: list[tuple[str, str | None]] = []
        self._log_window: tk.Toplevel | None = None
        self._current = ""
        root.title("ScrapCV")
        root.geometry("1440x900")
        root.minsize(1180, 700)
        try:
            root.state("zoomed")  # Windows: maximizada; con escalado de pantalla las tres columnas lo necesitan
        except tk.TclError:
            pass
        apply_style(root)
        self._build()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(POLL_MS, self._poll)
        root.after(50, self._first_view)

    # --- Construcción -------------------------------------------------------------------------------
    def _build(self) -> None:
        root = self._root
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        scale = max(1.0, root.winfo_fpixels("1i") / 96)  # escalado de Windows (125 %, 150 %…)
        side = tk.Frame(root, background=SIDEBAR, width=int(250 * scale))
        side.grid(row=0, column=0, sticky="ns")
        side.pack_propagate(False)
        brand = tk.Frame(side, background=SIDEBAR, padx=24, pady=26)
        brand.pack(fill="x")
        tk.Label(brand, text="ScrapCV", background=SIDEBAR, foreground="#ffffff",
                 font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(brand, text="Tu CV a partir de tus entregas", background=SIDEBAR, foreground=SIDE_MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w")
        tk.Frame(side, background="#1f2a4d", height=1).pack(fill="x", padx=20, pady=(0, 14))

        self._nav = {
            "settings": NavItem(side, "1", "Conectar", "Canvas y tus datos", lambda: self._show("settings")),
            "evidence": NavItem(side, "2", "Mis entregas", "Lo que hiciste en clase", lambda: self._show("evidence")),
            "cv": NavItem(side, "3", "Mi CV", "A la medida de una vacante", lambda: self._show("cv")),
        }
        for item in self._nav.values():
            item.pack(fill="x", padx=10, pady=2)

        footer = tk.Frame(side, background=SIDEBAR, padx=24, pady=20)
        footer.pack(side="bottom", fill="x")
        self._engine = tk.Label(footer, text="", background="#1a2547", foreground=SIDE_TEXT, font=("Segoe UI", 9),
                                padx=10, pady=4)
        self._engine.pack(anchor="w")
        link = tk.Label(footer, text="Ver registro técnico", background=SIDEBAR, foreground=SIDE_MUTED,
                        font=("Segoe UI", 8, "underline"), cursor="hand2")
        link.pack(anchor="w", pady=(10, 0))
        link.bind("<Button-1>", lambda _e: self._open_log())

        self._content = ttk.Frame(root)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.rowconfigure(0, weight=1)
        self._content.columnconfigure(0, weight=1)
        self._views = {
            "welcome": WelcomeView(self._content, lambda: self._show("settings"), self._run_demo),
            "settings": SettingsView(self._content, self._controller, self.start, self._on_settings_applied),
            "evidence": EvidenceView(self._content, self._controller, self.start, lambda: self._show("cv")),
            "cv": CvView(self._content, self._controller, self.start),
        }
        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")
        self._toast = ProgressToast(self._content)

    def _show(self, name: str) -> None:
        self._current = name
        self._views[name].tkraise()
        for key, item in self._nav.items():
            item.set_state(active=key == name)
        self._refresh_views()

    # --- Tareas en segundo plano ------------------------------------------------------------------------
    def start(self, name: str, work: Callable[[ProgressListener], Any], on_success: Callable[[Any], None] | None = None) -> None:
        if not self._runner.start(name, work, on_success):
            messagebox.showinfo("ScrapCV", "Espera un momento: todavía estoy terminando lo anterior.")
            return
        self._log(f"▶ {name}")
        self._toast.show(_TASK_TITLES.get(name, f"{name}…"))

    def _poll(self) -> None:
        try:
            while True:
                event = self._runner.events.get_nowait()
                if event.kind in ("info", "warning"):
                    message = REDACTOR.redact(event.payload)
                    self._log(message, "warning" if event.kind == "warning" else None)
                    if event.kind == "info":
                        if message.startswith(_HEADLINES):  # lo demás (archivos, líneas…) solo va al registro
                            self._toast.step(title=message, detail="")
                            self._views["cv"].show_progress(message)
                elif event.kind == "progress":
                    done, total = event.payload
                    self._toast.progress(done, total)
                    self._toast.step(detail=f"{min(done + 1, total)} de {total}" if total > 1 else "")
                elif event.kind in ("done", "failed"):
                    self._finish(event.payload)
        except queue.Empty:
            pass
        self._root.after(POLL_MS, self._poll)

    def _finish(self, outcome: TaskOutcome) -> None:
        if outcome.error is None:
            self._log(f"✔ {outcome.name} terminado.", "ok")
            self._toast.finish(True, "¡Listo!")
            if outcome.on_success:
                outcome.on_success(outcome.result)
            self._refresh_views()
            return
        title, message = friendly_error(outcome.error)
        log.error("%s falló: %r", outcome.name, outcome.error)
        self._log(f"✖ {outcome.name}: {REDACTOR.redact(str(outcome.error))}", "error")
        self._toast.finish(False, title)
        for key in ("settings", "evidence", "cv"):
            self._views[key].task_failed()
        messagebox.showerror(f"ScrapCV · {title}", message)

    # --- Registro técnico (oculto por defecto) -------------------------------------------------------------
    def _log(self, message: str, tag: str | None = None) -> None:
        line = (f"{datetime.now():%H:%M:%S}  {message}\n", tag)
        self._log_lines = (self._log_lines + [line])[-3000:]
        if self._log_window is not None and self._log_window.winfo_exists():
            self._log_text.configure(state="normal")
            self._log_text.insert("end", line[0], tag or ())
            self._log_text.see("end")
            self._log_text.configure(state="disabled")

    def _open_log(self) -> None:
        if self._log_window is not None and self._log_window.winfo_exists():
            self._log_window.lift()
            return
        self._log_window = window = tk.Toplevel(self._root, background=BG)
        window.title("ScrapCV · Registro técnico")
        window.geometry("900x500")
        frame, self._log_text = scrolled_text(window, font=(MONO[0], 9))
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        for tag, color in (("warning", "#b54708"), ("error", "#b42318"), ("ok", "#12805c")):
            self._log_text.tag_configure(tag, foreground=color)
        for text, tag in self._log_lines:
            self._log_text.insert("end", text, tag or ())
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    # --- Flujo entre pantallas -----------------------------------------------------------------------------
    def _first_view(self) -> None:
        try:
            total, _usable = self._controller.app.readiness()
        except Exception:  # p. ej. falta el token: empieza por la bienvenida
            total = 0
        self._show("cv" if total else "welcome")

    def _run_demo(self) -> None:
        settings = replace(self._controller.settings, use_demo=True)

        def work(progress: ProgressListener):
            progress.info("Preparando el ejemplo…")
            app = self._controller.apply(settings, None, False)
            app.run_all(progress)
            return app

        def done(_app) -> None:
            self._connected = True
            self._show("cv")

        self.start("Ejemplo", work, done)

    def _on_settings_applied(self) -> None:
        self._connected = True
        self._show("evidence")

    def _refresh_views(self) -> None:
        if self._runner.busy:  # el índice se está escribiendo en otro hilo
            return
        try:
            app = self._controller.app
            self._views["evidence"].refresh()
            self._views["cv"].refresh()
            total, usable = app.readiness()
            uses_ai = not app.profiler_name.startswith("perfil")
            self._engine.configure(text=f"●  IA local: {app.profiler_name.removeprefix('ollama:')}" if uses_ai
                                   else "○  Sin IA · redacción con reglas")
            done = {"settings": self._connected or total > 0, "evidence": usable > 0, "cv": self._views["cv"].has_cv}
        except Exception as exc:  # p. ej. falta el token con Canvas real
            self._log(f"Sin conexión: {exc}", "warning")
            done = {"settings": False, "evidence": False, "cv": False}
        for key, item in self._nav.items():
            item.set_state(done=done[key])

    def _close(self) -> None:
        if self._views["cv"].has_unsaved_changes and not messagebox.askyesno(
            "ScrapCV", "Tu CV tiene cambios sin guardar. ¿Salir de todos modos?"
        ):
            return
        if self._runner.busy and not messagebox.askyesno(
            "ScrapCV", "Todavía estoy trabajando. Si sales ahora se detiene (lo ya descargado no se pierde). ¿Salir?"
        ):
            return
        self._root.destroy()
