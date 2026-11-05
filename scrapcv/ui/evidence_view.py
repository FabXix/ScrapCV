"""Pestaña de evidencia: ejecutar las etapas 1 a 3 y revisar cada entrega."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk

from scrapcv.domain.models import IndexEntry, Stage, StageStatus
from scrapcv.ui.controller import AppController
from scrapcv.ui.widgets import MONO, TaskStarter, scrolled_text, scrolled_tree, set_text

_ICONS = {
    StageStatus.OK: "✔ ok",
    StageStatus.PARTIAL: "◐ parcial",
    StageStatus.FLAGGED: "⚑ marcado",
    StageStatus.ERROR: "✖ error",
    StageStatus.PENDING: "·",
}


class EvidenceView(ttk.Frame):
    def __init__(self, parent: tk.Widget, controller: AppController, start: TaskStarter) -> None:
        super().__init__(parent, padding=16)
        self._controller = controller
        self._start = start
        self._entries: dict[str, IndexEntry] = {}
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(bar, text="▶ Ejecutar todo", style="Accent.TButton", command=self._run_all).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar, text="1 · Descargar entregas", command=self._ingest).pack(side="left")
        ttk.Button(bar, text="2 · Extraer hechos", command=self._extract).pack(side="left", padx=6)
        ttk.Button(bar, text="3 · Generar perfiles", command=self._profiles).pack(side="left")
        ttk.Button(bar, text="↻", width=3, command=self.refresh).pack(side="right")

        ttk.Label(
            self,
            text="Cada etapa lee la salida de la anterior desde disco: puedes repetir una sin rehacer las demás. "
                 "Selecciona una entrega para ver sus hechos y su perfil.",
            style="Muted.TLabel", wraplength=900, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(8, 8))

        panes = ttk.PanedWindow(self, orient="vertical")
        panes.grid(row=2, column=0, sticky="nsew")
        table, self._tree = scrolled_tree(panes, {
            "tarea": ("Entrega", 300), "materia": ("Materia", 220), "grupal": ("Equipo", 60),
            "calif": ("Calif.", 70), "ingesta": ("Ingesta", 90), "extraccion": ("Extracción", 100),
            "perfil": ("Perfil", 90),
        }, height=9)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())
        details, self._details = scrolled_text(panes, height=12, font=MONO)
        self._details.configure(state="disabled")
        panes.add(table, weight=3)
        panes.add(details, weight=2)

    # --- Acciones ------------------------------------------------------------------
    def _run_all(self) -> None:
        self._start("ejecutar todo", lambda p: self._controller.app.run_all(p), lambda _r: self.refresh())

    def _ingest(self) -> None:
        self._start("ingesta", lambda p: self._controller.app.ingest(p), lambda _r: self.refresh())

    def _extract(self) -> None:
        self._start("extracción", lambda p: self._controller.app.extract(p), lambda _r: self.refresh())

    def _profiles(self) -> None:
        self._start("perfiles", lambda p: self._controller.app.build_profiles(p), lambda _r: self.refresh())

    # --- Presentación -------------------------------------------------------------------
    def refresh(self) -> None:
        selected = self._tree.selection()
        self._tree.delete(*self._tree.get_children())
        self._entries = {e.key: e for e in self._controller.app.entries()}
        for entry in self._entries.values():
            grade = "—" if entry.score is None else f"{entry.score:g}/{entry.points_possible or 0:g}"
            self._tree.insert("", "end", iid=entry.key, values=(
                entry.assignment_name, entry.course_name, "sí" if entry.is_group else "",
                grade, *(_ICONS[entry.stage(s).status] for s in Stage),
            ))
        if selected and self._tree.exists(selected[0]):
            self._tree.selection_set(selected[0])

    def _show_selected(self) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        entry = self._entries[selection[0]]
        app = self._controller.app
        lines = [f"{entry.assignment_name}  ·  {entry.course_name}", f"Carpeta: data/raw/{entry.key}", ""]
        for stage in Stage:
            result = entry.stage(stage)
            lines.append(f"[{stage.value}] {result.status.value}")
            lines += [f"    · {reason}" for reason in result.reasons]
        facts, profile = app.facts(entry.key), app.profile(entry.key)
        if profile:
            lines += ["", f"── perfil.json ({profile.origin}) ──", profile.summary]
            if profile.technologies:
                lines.append("Tecnologías: " + ", ".join(profile.technologies))
            if profile.skills:
                lines.append("Habilidades: " + ", ".join(profile.skills))
            if profile.role:
                lines.append("Rol: " + profile.role)
        if facts:
            data = facts.to_dict()
            data.pop("key", None)
            lines += ["", "── facts.json ──", json.dumps(data, indent=2, ensure_ascii=False)]
        set_text(self._details, "\n".join(lines))
