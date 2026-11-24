"""Paso 2 · Mis entregas: traerlas de Canvas, leerlas y revisar qué encontró ScrapCV."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import Callable

from scrapcv.domain.models import IndexEntry, Stage, StageStatus
from scrapcv.ui.controller import AppController
from scrapcv.ui.widgets import (
    INK,
    MUTED,
    OK,
    WARN,
    DANGER,
    Collapsible,
    StatCard,
    TaskStarter,
    page_header,
    scrolled_text,
    scrolled_tree,
    set_text,
    tip,
)

_STATE = {
    StageStatus.OK: "✔ Lista",
    StageStatus.PARTIAL: "✔ Lista",
    StageStatus.FLAGGED: "⚑ Sin contenido legible",
    StageStatus.ERROR: "✖ No se pudo descargar",
    StageStatus.PENDING: "· Pendiente",
}


def _overall(entry: IndexEntry) -> str:
    """Un solo estado legible por entrega (el peor de sus etapas)."""
    for status in (StageStatus.ERROR, StageStatus.FLAGGED, StageStatus.PENDING, StageStatus.PARTIAL):
        if any(entry.stage(s).status == status for s in Stage):
            return _STATE[status]
    return _STATE[StageStatus.OK]


class EvidenceView(ttk.Frame):
    def __init__(self, parent: tk.Widget, controller: AppController, start: TaskStarter,
                 on_ready: Callable[[], None] | None = None) -> None:
        super().__init__(parent, padding=(32, 26))
        self._controller = controller
        self._start = start
        self._on_ready = on_ready or (lambda: None)
        self._entries: dict[str, IndexEntry] = {}
        self.summary = tk.StringVar(value="")
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        head.columnconfigure(0, weight=1)
        page_header(head, "Mis entregas",
                    "ScrapCV lee lo que entregaste en Canvas (documentos, presentaciones y código) y resume cada "
                    "proyecto. La primera vez puede tardar unos minutos; después solo trae lo nuevo.").grid(
            row=0, column=0, sticky="ew")

        stats = ttk.Frame(self)
        stats.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        self._stat_total = StatCard(stats, "entregas encontradas")
        self._stat_ready = StatCard(stats, "listas para tu CV", OK)
        self._stat_warn = StatCard(stats, "sin contenido legible", DANGER)
        for card_widget in (self._stat_total, self._stat_ready, self._stat_warn):
            card_widget.pack(side="left", padx=(0, 12))

        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew")
        self._run_btn = tip(ttk.Button(bar, text="⤓  Traer mis entregas de Canvas", style="Accent.TButton",
                                       command=self._run_all),
                            "Descarga, lee y resume todo en un solo paso. Puedes repetirlo cuando entregues algo nuevo.")
        self._run_btn.pack(side="left")
        ttk.Label(bar, textvariable=self.summary, style="Muted.TLabel").pack(side="left", padx=16)
        self._next_btn = ttk.Button(bar, text="Continuar a Mi CV  →", style="Accent.TButton", command=self._on_ready)

        steps = Collapsible(self, "Pasos por separado (si algo falló o cambiaste de modelo)", style="Bg")
        steps.grid(row=3, column=0, sticky="ew", pady=(10, 8))
        for text, command, help_text in (
            ("1 · Descargar", self._ingest, "Solo baja de Canvas lo que falte."),
            ("2 · Leer archivos", self._extract, "Vuelve a leer código y documentos ya descargados."),
            ("3 · Resumir proyectos", self._profiles, "Vuelve a resumir con la IA (útil si cambiaste de modelo)."),
        ):
            tip(ttk.Button(steps.body, text=text, command=command), help_text).pack(side="left", padx=(0, 6))

        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.grid(row=4, column=0, sticky="nsew")
        table, self._tree = scrolled_tree(panes, {
            "tarea": ("Entrega", 320), "materia": ("Materia", 230), "estado": ("Estado", 170), "calif": ("Calif.", 70),
        }, height=12)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())
        self._tree.tag_configure("problem", foreground=MUTED)
        self._tree.tag_configure("odd", background="#f8f9fc")
        details, self._details = scrolled_text(panes, width=52, font=("Segoe UI", 9), padx=14, pady=12)
        t = self._details
        t.tag_configure("h", font=("Segoe UI Semibold", 12), foreground=INK, spacing3=4)
        t.tag_configure("sub", font=("Segoe UI Semibold", 10), foreground=INK, spacing1=10, spacing3=2)
        t.tag_configure("muted", foreground=MUTED)
        t.tag_configure("ok", foreground=OK)
        t.tag_configure("warn", foreground=WARN)
        t.tag_configure("mono", font=("Consolas", 8), foreground=MUTED)
        set_text(t, "Selecciona una entrega para ver qué encontró ScrapCV.")
        panes.add(table, weight=3)
        panes.add(details, weight=2)

    # --- Acciones ------------------------------------------------------------------------------
    def _run_all(self) -> None:
        self._run_btn.state(["disabled"])
        self._start("Traer entregas", lambda p: self._controller.app.run_all(p), lambda _r: self._done(True))

    def _ingest(self) -> None:
        self._start("Descargar", lambda p: self._controller.app.ingest(p), lambda _r: self._done(False))

    def _extract(self) -> None:
        self._start("Leer archivos", lambda p: self._controller.app.extract(p), lambda _r: self._done(False))

    def _profiles(self) -> None:
        self._start("Resumir proyectos", lambda p: self._controller.app.build_profiles(p), lambda _r: self._done(False))

    def _done(self, advance: bool) -> None:
        self._run_btn.state(["!disabled"])
        self.refresh()
        if advance and self._entries:
            self._on_ready()

    def task_failed(self) -> None:
        self._run_btn.state(["!disabled"])

    # --- Presentación ------------------------------------------------------------------------------
    def refresh(self) -> None:
        app = self._controller.app
        selected = self._tree.selection()
        self._tree.delete(*self._tree.get_children())
        self._entries = {e.key: e for e in app.entries()}
        problems = 0
        for i, entry in enumerate(self._entries.values()):
            grade = "—" if entry.score is None else f"{entry.score:g}/{entry.points_possible or 0:g}"
            state = _overall(entry)
            tags = ["odd"] if i % 2 else []
            if state[0] in "⚑✖":
                tags.append("problem")
                problems += 1
            self._tree.insert("", "end", iid=entry.key, values=(entry.assignment_name, entry.course_name, state, grade),
                              tags=tags)
        if selected and self._tree.exists(selected[0]):
            self._tree.selection_set(selected[0])
        total, usable = app.readiness()
        self._stat_total.set(total)
        self._stat_ready.set(usable)
        self._stat_warn.set(problems)
        if total:
            self.summary.set("Repítelo cuando entregues algo nuevo.")
            self._run_btn.configure(text="↻  Buscar entregas nuevas")
            self._next_btn.pack(side="right")
        else:
            self.summary.set("Todavía no hay entregas: presiona el botón para traerlas.")
            self._next_btn.pack_forget()

    def _show_selected(self) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        entry = self._entries[selection[0]]
        app = self._controller.app
        facts, profile = app.facts(entry.key), app.profile(entry.key)
        t = self._details
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", entry.assignment_name + "\n", "h")
        team = " · en equipo" if entry.is_group else ""
        t.insert("end", f"{entry.course_name}{team}\n", "muted")

        if profile and profile.summary:
            t.insert("end", "Resumen\n", "sub")
            t.insert("end", profile.summary + "\n")
            if profile.origin == "estatico":
                t.insert("end", "(resumen automático sin IA)\n", "muted")
        if facts:
            found = []
            if facts.languages:
                found.append("Lenguajes: " + ", ".join(sorted(facts.languages, key=lambda k: -facts.languages[k].lines)))
            techs = (profile.technologies if profile else []) or facts.dependencies[:8]
            if techs:
                found.append("Tecnologías: " + ", ".join(dict.fromkeys(techs)))
            if facts.documents:
                found.append("Documentos: " + ", ".join(sorted({d.kind.upper() for d in facts.documents})))
            for link in facts.links:
                found.append(f"Enlace ({link.kind}): {link.url}")
            if found:
                t.insert("end", "Lo que encontró ScrapCV\n", "sub")
                for line in found:
                    t.insert("end", f"•  {line}\n")
        notes = [r for s in Stage for r in entry.stage(s).reasons] + (profile.doubtful if profile else [])
        if notes:
            t.insert("end", "Avisos\n", "sub")
            for note in dict.fromkeys(notes):
                t.insert("end", f"⚠  {note}\n", "warn")
        elif facts:
            t.insert("end", "\n✔ Sin avisos.\n", "ok")
        if facts:
            data = facts.to_dict()
            data.pop("key", None)
            t.insert("end", "\nDetalles técnicos (facts.json)\n", "sub")
            t.insert("end", f"Carpeta: data/raw/{entry.key}\n", "mono")
            t.insert("end", json.dumps(data, indent=2, ensure_ascii=False) + "\n", "mono")
        t.configure(state="disabled")
