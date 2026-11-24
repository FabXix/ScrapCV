"""Paso 3 · Mi CV, con el flujo de Resume Optimizer:

    Vacante  ──►  CV a la medida (una hoja que se edita con clics)  ──►  Análisis: match, lo que tienes y lo que falta

Si no hay vacante, se usa un puesto del catálogo (o uno personalizado con palabras clave).
"""
from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from scrapcv.application.cv_service import CvResult
from scrapcv.ranking.match import MatchReport
from scrapcv.ranking.ranker import SelectionCriteria
from scrapcv.ranking.roles import JobRole
from scrapcv.ui.controller import AppController
from scrapcv.ui.resume_form import ResumeForm
from scrapcv.ui.widgets import (
    ACCENT,
    BORDER,
    DANGER,
    INK,
    MUTED,
    OK,
    WARN,
    Collapsible,
    ScoreRing,
    TaskStarter,
    autowrap,
    card,
    placeholder,
    scrolled_text,
    set_text,
    text_value,
    tip,
)
from scrapcv.writing.document import ResumeDocument

CUSTOM = "Personalizado…"
POSTING_HINT = ("Pega aquí la vacante completa: puesto, responsabilidades, requisitos y deseables.\n\n"
                "Tip: copia todo el texto del anuncio de LinkedIn, OCC o la bolsa de trabajo de tu universidad.")
EMPTY_CV = ("Tu CV aparecerá aquí, listo para editar.\n\n"
            "1.  Pega una vacante a la izquierda.\n"
            "2.  Presiona «Generar mi CV».\n"
            "3.  Revisa el análisis de la derecha, ajusta lo que quieras con un clic y descárgalo en PDF o Word.")
WORKING_CV = "✨  Armando tu CV…\n\nEstoy eligiendo tus mejores proyectos y redactando cada sección.\nCon IA puede tardar unos minutos."
_BUSY_PREFIXES = ("Leyendo", "Redactando", "Eligiendo", "Comparando", "Agrupando", "Consultando")


class CvView(ttk.Frame):
    def __init__(self, parent: tk.Widget, controller: AppController, start: TaskStarter) -> None:
        super().__init__(parent, padding=(24, 20))
        self._controller = controller
        self._start = start
        self._role: JobRole | None = None
        self._review: list[str] = []
        self._dirty = False
        self._saved = ""  # Markdown de la última versión generada o guardada
        self._template_key = ""
        self.role_name = tk.StringVar()
        self.keywords = tk.StringVar()
        self.max_projects = tk.IntVar(value=3)
        self.template_name = tk.StringVar()
        self.template_hint = tk.StringVar()
        self.status = tk.StringVar(value="")
        self._build()
        self._set_cv_actions(False)
        self._form.show_message(EMPTY_CV)

    # --- Construcción --------------------------------------------------------------------------------
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_header().grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        self._build_inputs().grid(row=1, column=0, sticky="nsw", padx=(0, 14))
        self._build_document().grid(row=1, column=1, sticky="nsew")
        self._build_analysis().grid(row=1, column=2, sticky="nse", padx=(14, 0))
        self.bind_all("<Control-s>", lambda _e: self._save() if self.winfo_ismapped() else None, add="+")

    def _build_header(self) -> ttk.Frame:
        head = ttk.Frame(self)
        titles = ttk.Frame(head)
        titles.pack(side="left")
        ttk.Label(titles, text="Mi CV", font=("Segoe UI Semibold", 20), foreground=INK).pack(anchor="w")
        ttk.Label(titles, textvariable=self.status, style="Muted.TLabel").pack(anchor="w")
        self._approve_btn = tip(ttk.Button(head, text="✔  Aprobar versión final", style="Accent.TButton",
                                           command=self._approve), "Guarda esta versión como tu CV final.")
        self._approve_btn.pack(side="right")
        self._word_btn = tip(ttk.Button(head, text="⤓  Word", command=lambda: self._export("docx")),
                             "Descarga el CV en Word (.docx) y lo abre.")
        self._word_btn.pack(side="right", padx=8)
        self._pdf_btn = tip(ttk.Button(head, text="⤓  PDF", command=lambda: self._export("html")),
                            "Abre el CV en el navegador con el diseño final; usa «Guardar como PDF».")
        self._pdf_btn.pack(side="right")
        self._save_btn = tip(ttk.Button(head, text="Guardar", command=self._save), "Guarda tus cambios (Ctrl+S).")
        self._save_btn.pack(side="right", padx=8)
        self._dirty_label = ttk.Label(head, text="", foreground=WARN)
        self._dirty_label.pack(side="right", padx=8)
        return head

    def _build_inputs(self) -> ttk.Frame:
        side = card(self, padding=18)
        ttk.Label(side, text="¿A qué vacante aplicas?", style="CardHeading.TLabel").pack(anchor="w")
        autowrap(ttk.Label(side, text="Pégala y elijo los proyectos que demuestran lo que piden.",
                           style="CardMuted.TLabel", justify="left")).pack(fill="x", pady=(2, 8))
        frame, self._posting = scrolled_text(side, height=12, width=36, font=("Segoe UI", 9), padx=10, pady=8)
        frame.pack(fill="x")
        placeholder(self._posting, POSTING_HINT)
        self._generate_btn = ttk.Button(side, text="✨  Generar mi CV", style="Accent.TButton", command=self._generate)
        self._generate_btn.pack(fill="x", pady=(12, 0))

        ttk.Separator(side).pack(fill="x", pady=14)
        ttk.Label(side, text="Estilo del CV", style="CardBold.TLabel").pack(anchor="w")
        self._template_box = ttk.Combobox(side, textvariable=self.template_name, width=34, state="readonly")
        self._template_box.pack(fill="x", pady=(4, 0))
        self._template_box.bind("<<ComboboxSelected>>", lambda _e: self._template_changed())
        autowrap(ttk.Label(side, textvariable=self.template_hint, style="CardMuted.TLabel",
                           justify="left")).pack(fill="x", pady=(4, 8))

        more = Collapsible(side, "Más opciones")
        more.pack(fill="x")
        body = more.body
        ttk.Label(body, text="Puesto (si no tienes vacante)", style="CardBold.TLabel").pack(anchor="w")
        self._roles = ttk.Combobox(body, textvariable=self.role_name, width=34)
        self._roles.pack(fill="x", pady=(2, 0))
        self._roles.bind("<<ComboboxSelected>>", lambda _e: self._toggle_keywords())
        self._kw_label = ttk.Label(body, text="Palabras clave (separadas por comas)", style="CardMuted.TLabel")
        self._kw_entry = ttk.Entry(body, textvariable=self.keywords)
        self._courses_label = ttk.Label(body, text="Materias a incluir", style="CardBold.TLabel")
        self._courses_label.pack(anchor="w", pady=(10, 0))
        self._courses = tk.Listbox(body, selectmode="multiple", height=5, exportselection=False, relief="flat",
                                   borderwidth=0, highlightthickness=1, highlightbackground=BORDER,
                                   highlightcolor=ACCENT, selectbackground="#e8eeff", selectforeground=INK,
                                   activestyle="none", font=("Segoe UI", 9))
        self._courses.pack(fill="x", pady=(2, 0))
        ttk.Label(body, text="Clic para quitar o poner una materia.", style="CardMuted.TLabel").pack(anchor="w")
        row = ttk.Frame(body, style="Inner.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Máximo de proyectos", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=1, to=10, width=4, textvariable=self.max_projects).pack(side="right")
        return side

    def _build_document(self) -> ttk.Frame:
        box = ttk.Frame(self)
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        self._form = ResumeForm(box, self._on_change)
        self._form.grid(row=0, column=0, sticky="nsew")
        ask = card(box, padding=(14, 10))
        ask.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        ask.columnconfigure(1, weight=1)
        ttk.Label(ask, text="✨  Pídele cambios a la IA", style="CardBold.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self._prompt = ttk.Entry(ask)
        self._prompt.grid(row=0, column=1, sticky="ew")
        self._prompt.insert(0, "")
        self._prompt.bind("<Return>", lambda _e: self._revise())
        tip(self._prompt, "Ej.: «hazlo más conciso», «resalta mi trabajo en equipo», «tono más formal». Enter aplica.")
        self._revise_btn = ttk.Button(ask, text="Aplicar", command=self._revise)
        self._revise_btn.grid(row=0, column=2, padx=(8, 0))
        return box

    def _build_analysis(self) -> ttk.Frame:
        panel = card(self, padding=18)
        panel.rowconfigure(3, weight=1)
        ttk.Label(panel, text="¿Qué tanto encajas?", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w")
        self._ring = ScoreRing(panel, size=130)
        self._ring.grid(row=1, column=0, pady=(12, 4))
        self._ring_caption = ttk.Label(panel, text="Pega una vacante para calcularlo.", style="CardMuted.TLabel",
                                       justify="center", anchor="center")
        autowrap(self._ring_caption).grid(row=2, column=0, sticky="ew", pady=(0, 10))

        frame, self._insights = scrolled_text(panel, width=36, font=("Segoe UI", 9), padx=10, pady=8, spacing1=2)
        frame.grid(row=3, column=0, sticky="nsew")
        t = self._insights
        t.tag_configure("h", font=("Segoe UI Semibold", 10), foreground=INK, spacing1=12, spacing3=4)
        t.tag_configure("ok", foreground=OK)
        t.tag_configure("gap", foreground=DANGER)
        t.tag_configure("warn", foreground=WARN)
        t.tag_configure("muted", foreground=MUTED)
        t.tag_configure("item", lmargin1=4, lmargin2=20)
        set_text(t, "Aquí verás lo que ya demuestras, lo que te falta y cómo mejorar tu CV.")
        return panel

    # --- Datos ----------------------------------------------------------------------------------------------
    def _template_options(self) -> dict[str, tuple[str, str, int | None]]:
        """nombre visible → (clave, descripción, proyectos sugeridos)."""
        return {t.name: (t.key, t.description, t.default_projects) for t in self._controller.app.resume_templates()}

    def _template_changed(self) -> None:
        _key, hint, projects = self._template_options()[self.template_name.get()]
        self.template_hint.set(hint)
        if projects:
            self.max_projects.set(projects)

    def refresh(self) -> None:
        app = self._controller.app
        settings = self._controller.settings
        options = self._template_options()
        self._template_box.configure(values=list(options))
        if self.template_name.get() not in options:
            saved = next((name for name, (key, _h, _p) in options.items() if key == settings.template_key), None)
            self.template_name.set(saved or next(iter(options)))
            self._template_changed()
        if not text_value(self._posting).strip() and settings.last_posting:
            self._posting.delete("1.0", "end")
            self._posting.insert("1.0", settings.last_posting)
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
        if not self._role and not self.status.get().startswith(_BUSY_PREFIXES):
            total, usable = app.readiness()
            self.status.set(f"Tienes {usable} proyectos listos para usarse." if total
                            else "Primero trae tus entregas en «Mis entregas».")

    def _toggle_keywords(self) -> None:
        custom = self.role_name.get() not in self._controller.app.roles.names()
        if custom:
            if self.role_name.get() == CUSTOM:
                self.role_name.set("")
            self._kw_label.pack(anchor="w", pady=(6, 0), before=self._courses_label)
            self._kw_entry.pack(fill="x", before=self._courses_label)
        else:
            self._kw_label.pack_forget()
            self._kw_entry.pack_forget()

    def _selected_courses(self) -> list[str]:
        return [self._courses.get(i) for i in self._courses.curselection()]

    def _set_cv_actions(self, enabled: bool) -> None:
        for button in (self._save_btn, self._pdf_btn, self._word_btn, self._approve_btn, self._revise_btn):
            button.state(["!disabled"] if enabled else ["disabled"])

    # --- Edición ------------------------------------------------------------------------------------------
    def _markdown(self) -> str:
        return self._form.document().to_markdown() if self._form.has_document else ""

    def _on_change(self) -> None:
        self._mark_dirty(bool(self._role) and self._markdown() != self._saved)

    def _mark_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._dirty_label.configure(text="●  Cambios sin guardar" if dirty else "")

    def _load(self, markdown: str) -> None:
        self._form.load(ResumeDocument.from_markdown(markdown))
        self._saved = self._markdown()
        self._mark_dirty(False)

    # --- Acciones -------------------------------------------------------------------------------------------
    def _generate(self) -> None:
        if self._dirty and not messagebox.askyesno(
            "ScrapCV", "Tienes cambios sin guardar en el CV actual. ¿Generar uno nuevo de todos modos?"
        ):
            return
        try:
            limit = int(self.max_projects.get())
        except (ValueError, tk.TclError):
            messagebox.showwarning("ScrapCV", "El máximo de proyectos debe ser un número.")
            return
        criteria = SelectionCriteria(include_courses=frozenset(self._selected_courses()), max_projects=limit)
        key = self._template_options()[self.template_name.get()][0]
        posting = text_value(self._posting).strip()
        app = self._controller.app
        if not posting:
            try:
                role = self._controller.resolve_role(self.role_name.get(), self.keywords.get())
            except ValueError as exc:
                messagebox.showwarning("ScrapCV", str(exc))
                return
            if not messagebox.askyesno("ScrapCV", f"No pegaste una vacante. ¿Armo un CV general para «{role.name}»?\n\n"
                                                  "Con la vacante el CV queda mucho más a la medida."):
                self._posting.focus_set()
                return
            work = lambda p: app.generate_cv(role, criteria, key, p)  # noqa: E731
        else:
            work = lambda p: app.generate_for_posting(posting, criteria, key, p)  # noqa: E731
        self._controller.remember_cv_inputs(posting, key)
        self._template_key = key
        self._role = None
        self._set_cv_actions(False)
        self._mark_dirty(False)
        self._form.show_message(WORKING_CV)
        self.status.set("Leyendo la vacante…" if posting else "Eligiendo tus mejores proyectos…")
        self._generate_btn.state(["disabled"])
        self._generate_btn.configure(text="Generando…")
        self._start("Generar CV", work, self._show_result)

    def show_progress(self, message: str) -> None:
        """La ventana reenvía aquí los mensajes de la tarea en curso."""
        if str(self._generate_btn.cget("text")).startswith("Generando") and message.startswith(_BUSY_PREFIXES):
            self.status.set(message)

    def task_failed(self) -> None:
        """La ventana avisa cuando una tarea termina con error."""
        self._generate_btn.state(["!disabled"])
        self._generate_btn.configure(text="✨  Generar mi CV")
        if not self._role:
            self._form.show_message(EMPTY_CV)
        else:
            self._set_cv_actions(True)
        if self.status.get().startswith(_BUSY_PREFIXES):
            self.status.set("No se pudo completar; revisa el mensaje.")

    def _show_result(self, result: CvResult) -> None:
        self._role = result.role
        self._review = list(result.review)
        self._load(result.markdown)
        self._set_cv_actions(True)
        self._show_analysis(result.report, result.review, len(result.ranked))
        pending = f" · {len(result.review)} cosas por revisar a la derecha" if result.review else ""
        self.status.set(f"✔ Listo: CV con {len(result.ranked)} proyectos{pending}. Haz clic en cualquier texto para editarlo.")
        self._generate_btn.state(["!disabled"])
        self._generate_btn.configure(text="✨  Generar de nuevo")

    def _show_analysis(self, report: MatchReport | None, review: list[str], projects: int) -> None:
        t = self._insights
        t.configure(state="normal")
        t.delete("1.0", "end")

        def heading(text: str) -> None:
            t.insert("end", text + "\n", "h")

        def item(mark: str, text: str, tag: str, detail: str = "") -> None:
            t.insert("end", f"{mark}  ", (tag, "item"))
            t.insert("end", text, ("item",))
            if detail:
                t.insert("end", f" — {detail}", ("item", "muted"))
            t.insert("end", "\n", ("item",))

        if report is None:
            self._ring.set(None)
            self._ring_caption.configure(text="CV general: pega una vacante para ver qué tanto encajas.")
        else:
            self._ring.set(report.percentage)
            verdict = ("¡Muy buen match! Envíalo con confianza." if report.percentage >= 70 else
                       "Buen punto de partida: revisa lo que te falta." if report.percentage >= 40 else
                       "Encajas poco con esta vacante; mira las sugerencias.")
            posting = report.posting
            self._ring_caption.configure(text=f"{posting.title}\n{verdict}")
            heading("✔  Lo que ya demuestras")
            for req in report.strengths:
                item("✔", req.name, "ok", "en " + ", ".join(req.projects[:2]))
            if not report.strengths:
                t.insert("end", "Todavía ningún requisito tiene evidencia.\n", "muted")
            if report.gaps:
                heading("✖  Lo que te falta")
                for req in report.gaps:
                    detail = f"lo tienes en «{req.elsewhere[0]}»" if req.elsewhere else (
                        "indispensable" if req.kind == "indispensable" else "deseable")
                    item("✖" if req.kind == "indispensable" else "○", req.name, "gap", detail)
            if report.tips:
                heading("→  Cómo mejorarlo")
                for tip_text in report.tips:
                    item("→", tip_text, "warn")
        if review:
            heading("⚠  Antes de enviarlo")
            for note in review:
                item("⚠", note, "warn")
        if not projects:
            heading("Sin proyectos")
            t.insert("end", "Ninguna entrega coincide. Revisa las materias en «Más opciones» o trae tus entregas "
                            "en «Mis entregas».\n", "muted")
        t.configure(state="disabled")

    def _revise(self) -> None:
        instruction = self._prompt.get().strip()
        if not self._role:
            return
        if not instruction:
            self._prompt.focus_set()
            return
        app = self._controller.app
        if not app.can_revise:
            messagebox.showinfo("ScrapCV", "Para pedir cambios activa «Redactar con IA» en Conectar y elige un modelo.")
            return
        markdown = self._markdown()
        self.status.set("Consultando a la IA…")
        self._start("Cambio de CV", lambda _p: app.revise_cv(markdown, instruction), self._show_revision)

    def _show_revision(self, revised: str) -> None:
        self._form.load(ResumeDocument.from_markdown(revised))
        self._prompt.delete(0, "end")
        self._on_change()
        self.status.set("✔ Cambio aplicado. Si te gusta, presiona Guardar.")

    def _save(self) -> None:
        if not self._role:
            return
        path = self._controller.app.save_cv(self._role, self._markdown(), self._template_key)
        self._saved = self._markdown()
        self._mark_dirty(False)
        self.status.set(f"✔ Guardado ({path.name}).")

    def _approve(self) -> None:
        if not self._role:
            return
        doc = self._form.document()
        missing_education = doc.education is not None and not (doc.education.degree and doc.education.school)
        pending = len(self._review) + int(missing_education)
        if pending and not messagebox.askyesno(
            "ScrapCV", f"Quedan {pending} punto(s) por revisar (a la derecha, «Antes de enviarlo»). "
                       "¿Aprobarlo de todos modos?"
        ):
            return
        path = self._controller.app.approve_cv(self._role, self._markdown(), self._template_key)
        self._saved = self._markdown()
        self._mark_dirty(False)
        self.status.set(f"✔ Versión final guardada ({path.name}). Descárgala en PDF o Word.")

    def _export(self, fmt: str) -> None:
        if not self._role:
            return
        try:
            path = self._controller.app.export_cv(self._role, self._markdown(), self._template_key, fmt)
        except PermissionError:
            messagebox.showerror("ScrapCV", "No pude guardar el archivo: probablemente está abierto en Word. "
                                            "Ciérralo e inténtalo de nuevo.")
            return
        self.status.set(f"✔ Descargado en la carpeta data/cv ({path.name}).")
        if fmt == "html":
            webbrowser.open(path.resolve().as_uri())
        elif hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]

    @property
    def has_unsaved_changes(self) -> bool:
        return self._dirty

    @property
    def has_cv(self) -> bool:
        return self._role is not None
