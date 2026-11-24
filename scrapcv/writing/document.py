"""El CV como documento estructurado.

La interfaz edita esta estructura (un campo por cosa: nombre, perfil, cada proyecto, cada logro), así el
usuario nunca ve Markdown. El Markdown sigue siendo el formato en disco y la entrada de los exportadores:
`to_markdown` y `from_markdown` convierten en ambos sentidos sin perder nada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scrapcv.writing.export import parse

_LINK = re.compile(r"^\[([^\]]+)\]\(([^)\s]+)\)$")
_DOMAIN = re.compile(r"^(?!.*@)[\w-]+(\.[\w-]+)+(/\S*)?$")
_SEP = "  ·  "


@dataclass
class ContactItem:
    text: str
    url: str = ""

    def to_markdown(self) -> str:
        url = self.url or (f"https://{self.text}" if _DOMAIN.match(self.text.strip()) else "")
        return f"[{self.text}]({url})" if url else self.text

    @classmethod
    def from_markdown(cls, value: str) -> "ContactItem":
        value = value.strip()
        match = _LINK.match(value)
        return cls(match.group(1), match.group(2)) if match else cls(value)


@dataclass
class ResumeProject:
    title: str
    meta: str = ""  # «Proyecto en equipo · Materia · Dic 2025»
    bullets: list[str] = field(default_factory=list)
    tools_label: str = "Herramientas"
    tools: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (etiqueta, url)


@dataclass
class ResumeEducation:
    degree: str = ""
    school: str = ""
    period: str = ""
    courses: list[str] = field(default_factory=list)


@dataclass
class ResumeDocument:
    name: str = ""
    headline: str = ""
    contact: list[ContactItem] = field(default_factory=list)
    intro_title: str = "Perfil profesional"
    intro: str = ""
    competencies: list[tuple[str, str]] = field(default_factory=list)
    projects: list[ResumeProject] = field(default_factory=list)
    skills: list[tuple[str, list[str]]] = field(default_factory=list)
    education: ResumeEducation | None = None
    order: list[str] = field(default_factory=lambda: ["intro", "projects", "skills", "education"])
    extra: list[tuple[str, str]] = field(default_factory=list)  # secciones que el usuario agregó a mano

    # --- Markdown -----------------------------------------------------------------------------------
    def to_markdown(self) -> str:
        out = [f"# {self.name.strip() or 'Tu nombre'}", ""]
        if self.headline.strip():
            out += [f"**{self.headline.strip()}**", ""]
        contact = [c.to_markdown() for c in self.contact if c.text.strip()]
        if contact:
            out += [_SEP.join(contact), ""]
        for section in self.order:
            out += getattr(self, f"_md_{section}")()
        for title, text in self.extra:
            if title.strip() and text.strip():
                out += [f"## {title.strip()}", "", text.strip(), ""]
        return "\n".join(out).rstrip() + "\n"

    def _md_intro(self) -> list[str]:
        return [f"## {self.intro_title}", "", self.intro.strip(), ""] if self.intro.strip() else []

    def _md_competencies(self) -> list[str]:
        items = [(t.strip(), d.strip()) for t, d in self.competencies if t.strip()]
        if not items:
            return []
        return ["## Competencias clave", ""] + [f"- **{t}:** {d}" if d else f"- **{t}**" for t, d in items] + [""]

    def _md_projects(self) -> list[str]:
        projects = [p for p in self.projects if p.title.strip()]
        if not projects:
            return []
        out = ["## Proyectos", ""]
        for p in projects:
            links = [f"[{label}]({url})" for label, url in p.links]
            out.append("### " + _SEP.join([p.title.strip(), *links]))
            if p.meta.strip():
                out.append(f"*{p.meta.strip()}*")
            out.append("")
            out += [f"- {b.strip()}" for b in p.bullets if b.strip()]
            tools = [t.strip() for t in p.tools if t.strip()]
            if tools:
                out.append(f"- **{p.tools_label}:** {', '.join(tools)}")
            out.append("")
        return out

    def _md_skills(self) -> list[str]:
        rows = [(c.strip(), [i.strip() for i in items if i.strip()]) for c, items in self.skills]
        rows = [(c, items) for c, items in rows if c and items]
        if not rows:
            return []
        return ["## Habilidades", ""] + [f"- **{c}:** {', '.join(items)}" for c, items in rows] + [""]

    def _md_education(self) -> list[str]:
        e = self.education
        if e is None:
            return []
        first = f"**{e.degree.strip() or '[Carrera]'}** — {e.school.strip() or '[Institución]'}"
        first += f" · {e.period.strip()}" if e.period.strip() else ""
        out = ["## Educación", "", first, ""]
        courses = [c.strip() for c in e.courses if c.strip()]
        if courses:
            out += [f"Materias relevantes: {', '.join(courses)}", ""]
        return out

    @classmethod
    def from_markdown(cls, markdown: str) -> "ResumeDocument":
        doc = cls(order=[])
        blocks = parse(markdown)
        section = ""
        project: ResumeProject | None = None
        for block in blocks:
            if block.kind == "h1":
                doc.name = block.text
                section = "header"
            elif block.kind == "h2":
                section, project = _section_key(block.text), None
                if section == "intro":
                    doc.intro_title = block.text
                if section == "education":
                    doc.education = ResumeEducation()
                if section == "extra":
                    doc.extra.append((block.text, ""))
                elif section not in doc.order:
                    doc.order.append(section)
            elif section == "header" and block.kind == "p":
                headline = re.fullmatch(r"\*\*(.+)\*\*", block.text)
                if headline and not doc.headline:
                    doc.headline = headline.group(1)
                else:
                    doc.contact += [ContactItem.from_markdown(part) for part in re.split(r"\s+·\s+", block.text)]
            elif section == "intro" and block.kind == "p":
                doc.intro = (doc.intro + "\n\n" + block.text).strip()
            elif section == "competencies" and block.kind == "ul":
                for item in block.items:
                    match = re.match(r"\*\*(.+?):?\*\*:?\s*(.*)$", item)
                    doc.competencies.append((match.group(1), match.group(2)) if match else (item, ""))
            elif section == "projects" and block.kind == "h3":
                title, *links = [part.strip() for part in re.split(r"\s{2,}·\s{2,}", block.text)]
                parsed = [(_LINK.match(link).group(1), _LINK.match(link).group(2)) for link in links if _LINK.match(link)]
                project = ResumeProject(title, links=parsed)
                doc.projects.append(project)
            elif section == "projects" and project and block.kind == "p" and block.is_meta:
                project.meta = block.text[1:-1]
            elif section == "projects" and project and block.kind == "ul":
                for item in block.items:
                    tools = re.match(r"\*\*(Tecnologías|Herramientas):\*\*\s*(.*)$", item)
                    if tools:
                        project.tools_label = tools.group(1)
                        project.tools = [t.strip() for t in tools.group(2).split(",") if t.strip()]
                    else:
                        project.bullets.append(item)
            elif section == "skills" and block.kind == "ul":
                for item in block.items:
                    match = re.match(r"\*\*(.+?):\*\*\s*(.*)$", item)
                    if match:
                        doc.skills.append((match.group(1), [s.strip() for s in match.group(2).split(",") if s.strip()]))
            elif section == "education" and block.kind == "p" and doc.education is not None:
                courses = re.match(r"Materias relevantes:\s*(.*)$", block.text)
                first = re.match(r"\*\*(.+?)\*\*\s*—\s*([^·]+?)(?:\s*·\s*(.+))?$", block.text)
                if courses:
                    doc.education.courses = [c.strip() for c in courses.group(1).split(",") if c.strip()]
                elif first:
                    degree, school = first.group(1), first.group(2).strip()
                    doc.education.degree = "" if degree == "[Carrera]" else degree
                    doc.education.school = "" if school == "[Institución]" else school
                    doc.education.period = (first.group(3) or "").strip()
            elif section == "extra" and doc.extra:
                title, text = doc.extra[-1]
                body = block.text if block.kind == "p" else "\n".join(f"- {i}" for i in block.items)
                doc.extra[-1] = (title, (text + "\n\n" + body).strip())
        return doc


def _section_key(title: str) -> str:
    low = title.lower()
    if "perfil" in low or "objetivo" in low or "resumen" in low:
        return "intro"
    if "competencia" in low:
        return "competencies"
    if "proyecto" in low or "experiencia" in low:
        return "projects"
    if "habilidad" in low:
        return "skills"
    if "educaci" in low or "formaci" in low:
        return "education"
    return "extra"
