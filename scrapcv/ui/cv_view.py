"""Pestaña del currículum: puesto, filtros, ranking, edición y aprobación."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from scrapcv.application.cv_service import EVIDENCE_KEY, CvResult
from scrapcv.ranking.ranker import SelectionCriteria
from scrapcv.ranking.roles import JobRole
from scrapcv.ui.controller import AppController
from scrapcv.ui.widgets import MONO, TaskStarter, scrolled_text, scrolled_tree, set_text

CUSTOM = "Personalizado…"
EVIDENCE_LABEL = "Borrador con evidencia (formato original)"


class CvView(ttk.Frame):
    def __init__(self, parent: tk.Widget, controller: AppController, start: TaskStarter) -> None:
        super().__init__(parent, padding=16)
        self._controller = controller
        self._start = start
        self._role: JobRole | None = None
        self.role_name = tk.StringVar()
        self.keywords = tk.StringVar()
        self.max_projects = tk.IntVar(value=3)
        self.template_name = tk.StringVar()
        self.template_hint = tk.StringVar()
        self._template_key = ""  # plantilla del borrador que se está editando
        self.status = tk.StringVar(value="Genera un borrador para el puesto que te interesa.")
        self._build()

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        side = ttk.Frame(self)
        side.grid(row=0, column=0, sticky="ns", padx=(0, 16))
        ttk.Label(side, text="Tipo de currículum").pack(anchor="w")
        self._template_box = ttk.Combobox(side, textvariable=self.template_name, width=38, state="readonly")
        self._template_box.pack(anchor="w", fill="x", pady=(2, 0))
        self._template_box.bind("<<ComboboxSelected>>", lambda _e: self._template_changed())
        ttk.Label(side, textvariable=self.template_hint, style="Muted.TLabel", wraplength=280, justify="left").pack(
            anchor="w", pady=(2, 8))
        ttk.Label(side, text="Puesto objetivo").pack(anchor="w")
        self._roles = ttk.Combobox(side, textvariable=self.role_name, width=38)
        self._roles.pack(anchor="w", fill="x", pady=(2, 8))
        self._roles.bind("<<ComboboxSelected>>", lambda _e: self._toggle_keywords())
        self._kw_label = ttk.Label(side, text="Palabras clave del puesto (separadas por comas)")
        self._kw_entry = ttk.Entry(side, textvariable=self.keywords)

        self._courses_label = ttk.Label(side, text="Materias a incluir")
        self._courses_label.pack(anchor="w", pady=(4, 0))
        box = ttk.Frame(side)
        box.pack(anchor="w", fill="x")
        self._courses = tk.Listbox(box, selectmode="multiple", height=8, exportselection=False, relief="solid", borderwidth=1)
        self._courses.pack(side="left", fill="x", expand=True)
        ttk.Label(side, text="Clic para quitar o poner una materia.", style="Muted.TLabel").pack(anchor="w")

        row = ttk.Frame(side)
        row.pack(anchor="w", pady=(10, 10))
        ttk.Label(row, text="Máximo de proyectos").pack(side="left")
        ttk.Spinbox(row, from_=1, to=15, width=4, textvariable=self.max_projects).pack(side="left", padx=8)
        ttk.Button(side, text="Generar CV", style="Accent.TButton", command=self._generate).pack(anchor="w", fill="x")

        ttk.Label(side, text="Ranking", font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(16, 2))
        table, self._ranking = scrolled_tree(side, {
            "proyecto": ("Proyecto", 170), "total": ("Total", 50), "afin": ("Afin.", 45),
            "tam": ("Tam.", 45), "cal": ("Cal.", 45),
        }, height=7)
        table.pack(anchor="w", fill="both", expand=True)

        editor = ttk.Frame(self)
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(0, weight=1)
        editor.rowconfigure(1, weight=1)
        ttk.Label(editor, text="Borrador (cv.md) — edítalo libremente antes de aprobarlo", font=("Segoe UI Semibold", 10)).grid(row=0, column=0, sticky="w")
        frame, self._editor = scrolled_text(editor, font=MONO, undo=True)
        frame.grid(row=1, column=0, sticky="nsew", pady=(4, 8))
        ask = ttk.LabelFrame(editor, text="Pedir cambios al modelo (Ollama)", style="Section.TLabelframe", padding=8)
        ask.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ask.columnconfigure(0, weight=1)
        self._prompt = tk.Text(ask, height=3, wrap="word", relief="solid", borderwidth=1, padx=6, pady=4)
        self._prompt.grid(row=0, column=0, sticky="ew")
        self._prompt.bind("<Control-Return>", lambda _e: (self._revise(), "break")[1])
        self._revise_btn = ttk.Button(ask, text="Aplicar cambio", command=self._revise)
        self._revise_btn.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        ttk.Label(
            ask, style="Muted.TLabel",
            text="Ej.: «hazlo más conciso», «resalta el trabajo en equipo». Ctrl+Enter aplica; Ctrl+Z en el borrador deshace.",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        actions = ttk.Frame(editor)
        actions.grid(row=3, column=0, sticky="ew")
        ttk.Button(actions, text="Guardar cambios", command=self._save).pack(side="left")
        ttk.Button(actions, text="✔ Aprobar como CV final", command=self._approve).pack(side="left", padx=6)
        ttk.Button(actions, text="Abrir carpeta", command=self._open_folder).pack(side="left")
        ttk.Label(actions, textvariable=self.status, style="Muted.TLabel").pack(side="left", padx=12)

    # --- Datos ---------------------------------------------------------------------------
    def _template_options(self) -> dict[str, tuple[str, str, int | None]]:
        """nombre visible → (clave, descripción, proyectos sugeridos)."""
        options = {t.name: (t.key, t.description, t.default_projects) for t in self._controller.app.resume_templates()}
        options[EVIDENCE_LABEL] = (EVIDENCE_KEY, "Lista cada proyecto con la evidencia que respalda cada viñeta. Útil para revisar.", None)
        return options

    def _template_changed(self) -> None:
        key, hint, projects = self._template_options()[self.template_name.get()]
        self.template_hint.set(hint)
        if projects:
            self.max_projects.set(projects)

    def refresh(self) -> None:
        app = self._controller.app
        options = self._template_options()
        self._template_box.configure(values=list(options))
        if self.template_name.get() not in options:
            self.template_name.set(next(iter(options)))
            self._template_changed()
        names = app.roles.names() + [CUSTOM]
        self._roles.configure(values=names)
        if not self.role_name.get():
            self.role_name.set(names[0])
        self._toggle_keywords()
        previous = set(self._selected_courses()) if self._courses.size() else None
        self._courses.delete(0, "end")
        for i, course in enumerate(app.course_names()):
            self._courses.insert("end", course)
            if previous is None or course in previous:
                self._courses.selection_set(i)

    def _toggle_keywords(self) -> None:
        custom = self.role_name.get() not in self._controller.app.roles.names()
        if custom:
            if self.role_name.get() == CUSTOM:
                self.role_name.set("")
            self._kw_label.pack(anchor="w", before=self._courses_label)
            self._kw_entry.pack(anchor="w", fill="x", pady=(2, 8), before=self._courses_label)
            self._roles.focus_set()
        else:
            self._kw_label.pack_forget()
            self._kw_entry.pack_forget()

    def _selected_courses(self) -> list[str]:
        return [self._courses.get(i) for i in self._courses.curselection()]

    # --- Acciones ---------------------------------------------------------------------------
    def _generate(self) -> None:
        try:
            role = self._controller.resolve_role(self.role_name.get(), self.keywords.get())
            limit = int(self.max_projects.get())
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("ScrapCV", str(exc))
            return
        courses = self._selected_courses()
        criteria = SelectionCriteria(include_courses=frozenset(courses), max_projects=limit)
        self._role = role
        key = self._template_options()[self.template_name.get()][0]
        self._template_key = key
        self.status.set("Generando… (con Ollama puede tardar unos minutos)")
        self._start("CV", lambda _p: self._controller.app.generate_cv(role, criteria, key), self._show_result)

    def _show_result(self, result: CvResult) -> None:
        set_text(self._editor, result.markdown, readonly=False)
        self._ranking.delete(*self._ranking.get_children())
        for ranked in result.ranked:
            b = ranked.breakdown
            self._ranking.insert("", "end", values=(
                ranked.candidate.entry.assignment_name, f"{ranked.total:.2f}",
                *(f"{b[name].value:.2f}" for name in ("afinidad", "tamaño", "calificación")),
            ))
        self.status.set(f"Borrador guardado en {result.path.name} ({len(result.ranked)} proyectos).")

    def _revise(self) -> None:
        markdown, instruction = self._markdown(), self._prompt.get("1.0", "end-1c")
        if not markdown.strip():
            messagebox.showinfo("ScrapCV", "Primero genera un borrador.")
            return
        if not instruction.strip():
            return
        app = self._controller.app
        if not app.can_revise:
            messagebox.showinfo("ScrapCV", "Activa un modelo de Ollama en la pestaña Configuración para pedir cambios.")
            return
        self.status.set("Consultando al modelo…")
        self._start("Cambio de CV", lambda _p: app.revise_cv(markdown, instruction), self._show_revision)

    def _show_revision(self, revised: str) -> None:
        self._editor.edit_separator()
        set_text(self._editor, revised, readonly=False)
        self._editor.edit_separator()
        self._prompt.delete("1.0", "end")
        self.status.set("Cambio aplicado. Revísalo y pulsa «Guardar cambios».")

    def _markdown(self) -> str:
        return self._editor.get("1.0", "end-1c")

    def _save(self) -> None:
        if self._role and self._markdown().strip():
            path = self._controller.app.save_cv(self._role, self._markdown(), self._template_key)
            self.status.set(f"Cambios guardados en {path.name}.")

    def _approve(self) -> None:
        if not (self._role and self._markdown().strip()):
            return
        if "Verificar:" in self._markdown() and not messagebox.askyesno(
            "ScrapCV", "El borrador todavía tiene puntos marcados como «Verificar». ¿Aprobarlo de todos modos?"
        ):
            return
        path = self._controller.app.approve_cv(self._role, self._markdown(), self._template_key)
        self.status.set(f"✔ CV final guardado en {path.name}.")

    def _open_folder(self) -> None:
        folder = self._controller.app.data_dir / "cv"
        folder.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("ScrapCV", str(folder))
