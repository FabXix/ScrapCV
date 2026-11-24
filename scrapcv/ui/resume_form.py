"""Editor del CV con forma de documento: una hoja blanca donde cada parte se edita con un clic.

Nada de Markdown: el usuario ve su nombre en grande, el perfil, cada proyecto con sus logros, etc.
Puede agregar o quitar logros, mover proyectos y agregar secciones (Experiencia laboral, Idiomas…).
`document()` devuelve un `ResumeDocument`; el resto de la app se encarga de guardarlo y exportarlo.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from scrapcv.ui.widgets import ACCENT, BG, BORDER, INK, MUTED, SURFACE, tip
from scrapcv.writing.document import ContactItem, ResumeDocument, ResumeEducation, ResumeProject

_HOVER = "#e3e8f0"
_PLACEHOLDER = "#a3acba"
EXTRA_SECTIONS = ("Experiencia laboral", "Idiomas", "Certificaciones y cursos", "Voluntariado", "Logros y premios")


class Field(tk.Entry):
    """Texto de una línea que parece parte del documento; al pasar el mouse se nota que es editable."""

    def __init__(self, parent: tk.Widget, value: str, font, fg: str = INK, hint: str = "",
                 on_change: Callable[[], None] | None = None, width: int = 10) -> None:
        super().__init__(parent, font=font, foreground=fg, background=SURFACE, relief="flat", borderwidth=0,
                         highlightthickness=1, highlightbackground=SURFACE, highlightcolor=ACCENT,
                         insertbackground=INK, width=width)
        self._fg, self._hint, self._showing_hint = fg, hint, False
        self.insert(0, value)
        self.bind("<Enter>", lambda _e: self.configure(highlightbackground=_HOVER), add="+")
        self.bind("<Leave>", lambda _e: self.configure(highlightbackground=SURFACE), add="+")
        self.bind("<FocusIn>", self._hide_hint, add="+")
        self.bind("<FocusOut>", self._show_hint, add="+")
        if on_change:
            self.bind("<KeyRelease>", lambda _e: on_change(), add="+")
        self._show_hint()

    def _show_hint(self, _e=None) -> None:
        if self._hint and not super().get():
            self.insert(0, self._hint)
            self.configure(foreground=_PLACEHOLDER)
            self._showing_hint = True

    def _hide_hint(self, _e=None) -> None:
        if self._showing_hint:
            self.delete(0, "end")
            self.configure(foreground=self._fg)
            self._showing_hint = False

    def value(self) -> str:
        return "" if self._showing_hint else super().get().strip()


class Area(tk.Text):
    """Párrafo que crece con su contenido (sin barra de desplazamiento propia)."""

    def __init__(self, parent: tk.Widget, value: str, font, fg: str = INK, hint: str = "",
                 on_change: Callable[[], None] | None = None) -> None:
        super().__init__(parent, font=font, foreground=fg, background=SURFACE, relief="flat", borderwidth=0,
                         highlightthickness=1, highlightbackground=SURFACE, highlightcolor=ACCENT, wrap="word",
                         height=1, width=10, undo=True, padx=2, pady=1, insertbackground=INK, spacing2=2)
        self._hint = hint
        self.tag_configure("hint", foreground=_PLACEHOLDER)
        self.insert("1.0", value)
        self.bind("<Enter>", lambda _e: self.configure(highlightbackground=_HOVER), add="+")
        self.bind("<Leave>", lambda _e: self.configure(highlightbackground=SURFACE), add="+")
        self.bind("<FocusIn>", self._hide_hint, add="+")
        self.bind("<FocusOut>", self._show_hint, add="+")
        self.bind("<KeyRelease>", lambda _e: (self._fit(), on_change() if on_change else None), add="+")
        self.bind("<Configure>", lambda _e: self._fit(), add="+")
        self.bind("<Return>", lambda _e: "break" if self.get("1.0", "end-1c").count("\n") > 30 else None)
        self._show_hint()

    def _fit(self) -> None:
        try:
            lines = int(self.count("1.0", "end", "displaylines")[0])
        except (tk.TclError, TypeError):
            return
        if lines and lines != int(self.cget("height")):
            self.configure(height=lines)

    def _show_hint(self, _e=None) -> None:
        if self._hint and not self.get("1.0", "end-1c").strip():
            self.delete("1.0", "end")
            self.insert("1.0", self._hint, "hint")

    def _hide_hint(self, _e=None) -> None:
        if self.tag_ranges("hint"):
            self.delete("1.0", "end")

    def value(self) -> str:
        return "" if self.tag_ranges("hint") else self.get("1.0", "end-1c").strip()


def _action(parent: tk.Widget, text: str, command: Callable[[], None], help_text: str = "", danger: bool = False) -> tk.Label:
    """Botón con forma de enlace pequeño (✕, ↑, «+ Agregar logro»)."""
    color = "#c0392b" if danger else ACCENT
    label = tk.Label(parent, text=text, foreground=MUTED if danger else color, background=SURFACE, cursor="hand2",
                     font=("Segoe UI", 9))
    label.bind("<Button-1>", lambda _e: command())
    label.bind("<Enter>", lambda _e: label.configure(foreground=color))
    label.bind("<Leave>", lambda _e: label.configure(foreground=MUTED if danger else color))
    if help_text:
        tip(label, help_text)
    return label


class ResumeForm(ttk.Frame):
    def __init__(self, parent: tk.Widget, on_change: Callable[[], None]) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._doc: ResumeDocument | None = None
        self._canvas = tk.Canvas(self, background=BG, highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=bar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._paper = tk.Frame(self._canvas, background=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                               padx=44, pady=36)
        self._window = self._canvas.create_window(0, 16, anchor="n", window=self._paper)
        self._paper.bind("<Configure>", lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", self._resize)
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.show_message("")

    # --- Lienzo ------------------------------------------------------------------------------------------
    def _resize(self, event) -> None:
        width = max(420, min(event.width - 40, 900))
        self._canvas.coords(self._window, event.width / 2, 16)
        self._canvas.itemconfigure(self._window, width=width)

    def _wheel(self, event) -> None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is not None and str(widget).startswith(str(self)):
            self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _clear(self) -> None:
        for child in self._paper.winfo_children():
            child.destroy()

    def show_message(self, text: str) -> None:
        """Hoja con un mensaje (estado vacío)."""
        self._doc = None
        self._clear()
        tk.Label(self._paper, text=text, background=SURFACE, foreground=MUTED, font=("Segoe UI", 11),
                 justify="left", anchor="w", wraplength=560).pack(fill="x", pady=40)

    # --- Construcción del documento --------------------------------------------------------------------------
    def load(self, doc: ResumeDocument) -> None:
        position = self._canvas.yview()[0]
        self._doc = doc
        self._clear()
        changed = self._changed
        p = self._paper
        self._name = Field(p, doc.name, ("Segoe UI Semibold", 22), hint="Tu nombre", on_change=changed)
        self._name.pack(fill="x")
        self._headline = Field(p, doc.headline, ("Segoe UI Semibold", 12), fg=ACCENT,
                               hint="Puesto al que aplicas", on_change=changed)
        self._headline.pack(fill="x", pady=(2, 0))
        contact = "  ·  ".join(c.text for c in doc.contact)
        self._contact = Field(p, contact, ("Segoe UI", 9), fg=MUTED,
                              hint="correo  ·  teléfono  ·  ciudad  ·  linkedin.com/in/tu-nombre", on_change=changed)
        self._contact.pack(fill="x", pady=(4, 0))
        self._contact_links = {c.text: c.url for c in doc.contact if c.url}

        self._sections: dict[str, Callable[[ResumeDocument], None]] = {}
        for key in doc.order:
            getattr(self, f"_build_{key}")(doc)
        self._extras: list[tuple[Field, Area]] = []
        for title, text in doc.extra:
            self._build_extra(title, text)

        add = tk.Frame(p, background=SURFACE)
        add.pack(fill="x", pady=(22, 0))
        self._add_menu = tk.Menu(add, tearoff=False)
        for name in EXTRA_SECTIONS:
            self._add_menu.add_command(label=name, command=lambda n=name: self._add_extra(n))
        self._add_menu.add_command(label="Otra sección…", command=lambda: self._add_extra("Nueva sección"))
        button = _action(add, "+ Agregar sección (experiencia, idiomas, cursos…)", lambda: None,
                         "Agrega lo que Canvas no conoce: trabajos, idiomas, certificaciones, voluntariado.")
        button.bind("<Button-1>", lambda e: self._add_menu.tk_popup(e.x_root, e.y_root))
        button.pack(anchor="w")
        self.after_idle(lambda: self._canvas.yview_moveto(position))

    def _heading(self, text: str) -> tk.Frame:
        box = tk.Frame(self._paper, background=SURFACE)
        box.pack(fill="x", pady=(20, 6))
        tk.Label(box, text=text.upper(), background=SURFACE, foreground="#1e3a8a",
                 font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Frame(box, height=2, background="#c7d2fe").pack(fill="x", pady=(2, 0))
        return box

    def _build_intro(self, doc: ResumeDocument) -> None:
        self._heading(doc.intro_title or "Perfil profesional")
        self._intro = Area(self._paper, doc.intro, ("Segoe UI", 10),
                           hint="Dos o tres frases sobre quién eres y qué puedes aportar.", on_change=self._changed)
        self._intro.pack(fill="x")

    def _build_competencies(self, doc: ResumeDocument) -> None:
        self._heading("Competencias clave")
        self._competency_rows: list[tuple[Field, Field]] = []
        for i, (title, desc) in enumerate(doc.competencies):
            row = tk.Frame(self._paper, background=SURFACE)
            row.pack(fill="x", pady=1)
            t = Field(row, title, ("Segoe UI Semibold", 10), hint="Competencia", on_change=self._changed, width=22)
            t.pack(side="left")
            d = Field(row, desc, ("Segoe UI", 10), hint="Dónde la demostraste", on_change=self._changed)
            d.pack(side="left", fill="x", expand=True, padx=(6, 0))
            _action(row, "✕", lambda i=i: self._edit(lambda doc: doc.competencies.pop(i)), "Quitar", True).pack(side="right")
            self._competency_rows.append((t, d))
        _action(self._paper, "+ Agregar competencia",
                lambda: self._edit(lambda doc: doc.competencies.append(("", "")))).pack(anchor="w", pady=(4, 0))

    def _build_projects(self, doc: ResumeDocument) -> None:
        self._heading("Proyectos")
        self._project_rows = []
        for i, project in enumerate(doc.projects):
            box = tk.Frame(self._paper, background=SURFACE)
            box.pack(fill="x", pady=(8, 2))
            top = tk.Frame(box, background=SURFACE)
            top.pack(fill="x")
            title = Field(top, project.title, ("Segoe UI Semibold", 11), hint="Nombre del proyecto", on_change=self._changed)
            title.pack(side="left", fill="x", expand=True)
            _action(top, "✕ Quitar", lambda i=i: self._edit(lambda doc: doc.projects.pop(i)),
                    "Quita este proyecto del CV", True).pack(side="right", padx=(8, 0))
            if i < len(doc.projects) - 1:
                _action(top, "↓", lambda i=i: self._move(i, 1), "Bajar").pack(side="right", padx=4)
            if i > 0:
                _action(top, "↑", lambda i=i: self._move(i, -1), "Subir").pack(side="right", padx=4)
            meta = Field(box, project.meta, ("Segoe UI", 9, "italic"), fg=MUTED, hint="Materia · fecha",
                         on_change=self._changed)
            meta.pack(fill="x")
            if project.links:
                tk.Label(box, text="  ·  ".join(label for label, _url in project.links) + " (enlace incluido)",
                         background=SURFACE, foreground=ACCENT, font=("Segoe UI", 8)).pack(anchor="w")
            bullets = []
            for j, text in enumerate(project.bullets):
                row = tk.Frame(box, background=SURFACE)
                row.pack(fill="x", pady=1)
                tk.Label(row, text="•", background=SURFACE, foreground=MUTED, font=("Segoe UI", 10)).pack(side="left", anchor="n", padx=(4, 6))
                area = Area(row, text, ("Segoe UI", 10), hint="Qué hiciste y para qué sirvió", on_change=self._changed)
                area.pack(side="left", fill="x", expand=True)
                _action(row, "✕", lambda i=i, j=j: self._edit(lambda doc: doc.projects[i].bullets.pop(j)),
                        "Quitar este logro", True).pack(side="right", anchor="n", padx=(6, 0))
                bullets.append(area)
            tools_row = tk.Frame(box, background=SURFACE)
            tools_row.pack(fill="x", pady=(2, 0))
            tk.Label(tools_row, text=f"{project.tools_label}:", background=SURFACE, foreground=INK,
                     font=("Segoe UI Semibold", 9)).pack(side="left", padx=(4, 4))
            tools = Field(tools_row, ", ".join(project.tools), ("Segoe UI", 9), hint="Excel, Canva, Python…",
                          on_change=self._changed)
            tools.pack(side="left", fill="x", expand=True)
            _action(box, "+ Agregar logro", lambda i=i: self._edit(lambda doc: doc.projects[i].bullets.append("")),
                    "Agrega otra línea a este proyecto").pack(anchor="w", padx=(4, 0), pady=(2, 0))
            self._project_rows.append((title, meta, bullets, tools))
        _action(self._paper, "+ Agregar proyecto",
                lambda: self._edit(lambda doc: doc.projects.append(ResumeProject("", bullets=[""]))),
                "Por ejemplo un proyecto personal o de trabajo que no está en Canvas.").pack(anchor="w", pady=(10, 0))

    def _build_skills(self, doc: ResumeDocument) -> None:
        self._heading("Habilidades")
        self._skill_rows: list[tuple[Field, Field]] = []
        for i, (category, items) in enumerate(doc.skills):
            row = tk.Frame(self._paper, background=SURFACE)
            row.pack(fill="x", pady=1)
            c = Field(row, category, ("Segoe UI Semibold", 10), hint="Categoría", on_change=self._changed, width=24)
            c.pack(side="left")
            v = Field(row, ", ".join(items), ("Segoe UI", 10), hint="Separadas por comas", on_change=self._changed)
            v.pack(side="left", fill="x", expand=True, padx=(6, 0))
            _action(row, "✕", lambda i=i: self._edit(lambda doc: doc.skills.pop(i)), "Quitar", True).pack(side="right")
            self._skill_rows.append((c, v))
        _action(self._paper, "+ Agregar categoría (p. ej. Idiomas, Software)",
                lambda: self._edit(lambda doc: doc.skills.append(("", [])))).pack(anchor="w", pady=(4, 0))

    def _build_education(self, doc: ResumeDocument) -> None:
        self._heading("Educación")
        e = doc.education or ResumeEducation()
        row = tk.Frame(self._paper, background=SURFACE)
        row.pack(fill="x")
        self._degree = Field(row, e.degree, ("Segoe UI Semibold", 10), hint="Tu carrera", on_change=self._changed, width=34)
        self._degree.pack(side="left")
        tk.Label(row, text="—", background=SURFACE, foreground=MUTED).pack(side="left", padx=4)
        self._school = Field(row, e.school, ("Segoe UI", 10), hint="Tu universidad", on_change=self._changed, width=18)
        self._school.pack(side="left")
        self._period = Field(row, e.period, ("Segoe UI", 10), fg=MUTED, hint="2022 – 2026", on_change=self._changed, width=16)
        self._period.pack(side="right")
        courses = tk.Frame(self._paper, background=SURFACE)
        courses.pack(fill="x", pady=(4, 0))
        tk.Label(courses, text="Materias relevantes:", background=SURFACE, foreground=INK,
                 font=("Segoe UI", 9)).pack(side="left", padx=(2, 4))
        self._courses = Field(courses, ", ".join(e.courses), ("Segoe UI", 9), hint="Separadas por comas",
                              on_change=self._changed)
        self._courses.pack(side="left", fill="x", expand=True)

    def _build_extra(self, title: str, text: str) -> None:
        index = len(self._extras)
        box = tk.Frame(self._paper, background=SURFACE)
        box.pack(fill="x", pady=(20, 0))
        top = tk.Frame(box, background=SURFACE)
        top.pack(fill="x")
        heading = Field(top, title, ("Segoe UI Semibold", 10), fg="#1e3a8a", hint="Título de la sección",
                        on_change=self._changed)
        heading.pack(side="left", fill="x", expand=True)
        _action(top, "✕ Quitar sección", lambda: self._edit(lambda doc: doc.extra.pop(index)), "", True).pack(side="right")
        tk.Frame(box, height=2, background="#c7d2fe").pack(fill="x", pady=(2, 6))
        area = Area(box, text, ("Segoe UI", 10), hint=_EXTRA_HINTS.get(title, "Escribe aquí."), on_change=self._changed)
        area.pack(fill="x")
        self._extras.append((heading, area))

    # --- Cambios estructurales -----------------------------------------------------------------------------
    def _changed(self) -> None:
        self._on_change()

    def _edit(self, change: Callable[[ResumeDocument], object]) -> None:
        doc = self.document()
        change(doc)
        self.load(doc)
        self._on_change()

    def _move(self, index: int, step: int) -> None:
        def swap(doc: ResumeDocument) -> None:
            other = index + step
            doc.projects[index], doc.projects[other] = doc.projects[other], doc.projects[index]
        self._edit(swap)

    def _add_extra(self, title: str) -> None:
        self._edit(lambda doc: doc.extra.append((title, "")))
        self.after_idle(lambda: self._canvas.yview_moveto(1.0))

    # --- Lectura -----------------------------------------------------------------------------------------------
    @property
    def has_document(self) -> bool:
        return self._doc is not None

    def document(self) -> ResumeDocument:
        base = self._doc or ResumeDocument()
        doc = ResumeDocument(order=list(base.order), intro_title=base.intro_title)
        doc.name, doc.headline = self._name.value(), self._headline.value()
        parts = [part.strip() for part in self._contact.value().split("·") if part.strip()]
        doc.contact = [ContactItem(part, self._contact_links.get(part, "")) for part in parts]
        if "intro" in base.order:
            doc.intro = self._intro.value()
        if "competencies" in base.order:
            doc.competencies = [(t.value(), d.value()) for t, d in self._competency_rows]
        if "projects" in base.order:
            for (title, meta, bullets, tools), old in zip(self._project_rows, base.projects):
                doc.projects.append(ResumeProject(
                    title=title.value(), meta=meta.value(), bullets=[b.value() for b in bullets],
                    tools_label=old.tools_label, tools=[t.strip() for t in tools.value().split(",") if t.strip()],
                    links=list(old.links),
                ))
        if "skills" in base.order:
            doc.skills = [(c.value(), [s.strip() for s in v.value().split(",") if s.strip()]) for c, v in self._skill_rows]
        if "education" in base.order:
            doc.education = ResumeEducation(self._degree.value(), self._school.value(), self._period.value(),
                                            [c.strip() for c in self._courses.value().split(",") if c.strip()])
        doc.extra = [(h.value(), a.value()) for h, a in self._extras]
        return doc


_EXTRA_HINTS = {
    "Experiencia laboral": "Puesto — Empresa (fechas). Qué hacías y qué lograste.",
    "Idiomas": "Inglés — intermedio (B1)…",
    "Certificaciones y cursos": "Nombre del curso — Institución (año)",
    "Voluntariado": "Organización — qué hiciste y cuándo.",
    "Logros y premios": "Premio o reconocimiento — año",
}
