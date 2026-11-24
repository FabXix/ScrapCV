"""Armado del currículum a partir de una plantilla.

Responsabilidad única: decidir qué secciones lleva el CV, en qué orden y con qué datos. El texto de cada
sección lo redacta la cadena de escritores (`writers.py`); las tecnologías y habilidades salen de la evidencia.
El resultado es un `ResumeDocument` (lo que la interfaz edita) y su Markdown (lo que se guarda y exporta).

El CV está pensado para enviarse: nada de rutas, notas internas ni «Verificar» dentro del documento. Lo que
el usuario debe revisar va en `ResumeDraft.review` y la evidencia de cada parte en `ResumeDraft.evidence`.
Sirve para cualquier carrera: si no hay código, se habla de herramientas y habilidades profesionales.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from scrapcv.analysis.signals import soft_signals
from scrapcv.domain.models import ContactInfo, UserInfo
from scrapcv.domain.skills import CATEGORY_ORDER, LANGUAGES, PRACTICES, PROFESSIONAL, canonical
from scrapcv.domain.text import phrase_matches
from scrapcv.ports import NullProgress, ProgressListener
from scrapcv.ranking.ranker import RankedProject
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.document import ContactItem, ResumeDocument, ResumeEducation, ResumeProject
from scrapcv.writing.format import display_url, full_url, month_year, pretty_course, pretty_name
from scrapcv.writing.templates import TEMPLATES, ResumeTemplate, template_by_key
from scrapcv.writing.writers import WriterChain, WritingRequest, ranked_skills

__all__ = ["ResumeBuilder", "ResumeDraft", "TEMPLATES", "template_by_key"]

_LINK_LABELS = {"repositorio": "Repositorio", "figma": "Prototipo", "youtube": "Video"}
_INTERNAL_NOTES = ("sin modelo", "no respondió")
_SECTION_KEYS = {"summary": "intro", "objective": "intro", "competencies": "competencies", "projects": "projects",
                 "skills": "skills", "education": "education"}


@dataclass
class ResumeDraft:
    document: ResumeDocument
    review: list[str] = field(default_factory=list)  # lo que el usuario debe revisar antes de enviarlo
    evidence: list[dict] = field(default_factory=list)  # {"seccion", "texto", "evidencia": [rutas]}

    @property
    def markdown(self) -> str:
        return self.document.to_markdown()


@dataclass
class _Context:
    user: UserInfo
    contact: ContactInfo
    request: WritingRequest
    draft: ResumeDraft
    progress: ProgressListener

    @property
    def ranked(self) -> list[RankedProject]:
        return self.request.ranked

    @property
    def doc(self) -> ResumeDocument:
        return self.draft.document

    @property
    def has_code(self) -> bool:
        return any(r.candidate.facts.languages for r in self.ranked)

    def note(self, text: str | None) -> None:
        if text and text not in self.draft.review:
            self.draft.review.append(text)

    def trace(self, section: str, text: str, sources: list[str]) -> None:
        self.draft.evidence.append({"seccion": section, "texto": text, "evidencia": sources})


class ResumeBuilder:
    def __init__(self, writers: WriterChain) -> None:
        self._writers = writers

    @property
    def writer_name(self) -> str:
        return self._writers.name

    def build(self, user: UserInfo, contact: ContactInfo, role: JobRole, template: ResumeTemplate,
              ranked: list[RankedProject], progress: ProgressListener | None = None) -> ResumeDraft:
        request = WritingRequest(template, role, ranked, contact.degree.strip())
        order = list(dict.fromkeys(_SECTION_KEYS[s] for s in template.sections if s in _SECTION_KEYS))
        context = _Context(user, contact, request, ResumeDraft(ResumeDocument(order=order)), progress or NullProgress())
        steps = {
            "header": self._header,
            "summary": lambda c: self._intro(c, "Perfil profesional"),
            "objective": lambda c: self._intro(c, "Objetivo profesional"),
            "competencies": self._competencies,
            "projects": self._projects,
            "skills": self._skills,
            "education": self._education,
        }
        for name in template.sections:
            steps[name](context)
        return context.draft

    # --- Secciones ---------------------------------------------------------------------------------
    def _header(self, c: _Context) -> None:
        c.doc.name = pretty_name(c.user.name) or "Tu nombre"
        c.doc.headline = c.request.target
        items = [ContactItem(x.strip()) for x in (c.user.email, c.contact.phone, c.contact.location) if x and x.strip()]
        items += [ContactItem(display_url(v), full_url(v)) for v in (c.contact.linkedin, c.contact.github,
                                                                     c.contact.portfolio) if v.strip()]
        c.doc.contact = items
        wanted = [("LinkedIn", c.contact.linkedin), ("teléfono", c.contact.phone)]
        if c.has_code:
            wanted.insert(1, ("GitHub", c.contact.github))
        missing = [label for label, value in wanted if not value.strip()]
        if missing:
            c.note(f"Contacto: falta tu {', '.join(missing)}. Agrégalo en el paso 1 · Conectar › «Tus datos para el CV».")

    def _intro(self, c: _Context, title: str) -> None:
        c.progress.info(f"Redactando tu {title.lower()}…")
        text, note = self._writers.write(title, lambda w: w.summary(c.request))
        c.note(note)
        c.doc.intro_title, c.doc.intro = title, text or ""

    def _competencies(self, c: _Context) -> None:
        c.progress.info("Agrupando tus competencias clave…")
        items, note = self._writers.write("Competencias clave", lambda w: w.competencies(c.request))
        c.note(note)
        c.doc.competencies = list(items or [])

    def _projects(self, c: _Context) -> None:
        if not c.ranked:
            c.note("Proyectos: ninguna entrega coincide con la vacante. Revisa «Más opciones › Materias» o pega una "
                   "vacante más completa.")
            return
        for number, r in enumerate(c.ranked, start=1):
            entry, facts, profile = r.candidate.entry, r.candidate.facts, r.candidate.profile
            c.progress.info(f"Redactando proyecto {number} de {len(c.ranked)}: {entry.assignment_name}…")
            c.progress.progress(number - 1, len(c.ranked))
            text, note = self._writers.write("Proyectos", lambda w: w.project(c.request, r))
            c.note(note)
            if text is None:
                continue
            links = list(dict.fromkeys((_LINK_LABELS[link.kind], link.url) for link in facts.links
                                       if link.kind in _LINK_LABELS))
            meta = [m for m in ("Proyecto en equipo" if entry.is_group else "Proyecto académico",
                                pretty_course(entry.course_name), month_year(entry.submitted_at)) if m]
            tools = [s.name for s in r.candidate.skills() if s.category != PRACTICES][:6]
            uses_code = any(s.category == LANGUAGES for s in r.candidate.skills())
            c.doc.projects.append(ResumeProject(
                title=text.title, meta=" · ".join(meta), bullets=list(text.bullets),
                tools_label="Tecnologías" if uses_code else "Herramientas", tools=tools, links=links,
            ))
            sources = [f"raw/{entry.key}/{f}" for f in ((profile.sources if profile else []) or facts.evidence_files)[:4]]
            c.trace("Proyectos", text.title, sources + [f"raw/{entry.key}/{f}" for f in facts.dependency_files[:2]])
            for doubt in (profile.doubtful if profile else []):
                if not any(marker in doubt for marker in _INTERNAL_NOTES):
                    c.note(f"«{text.title}»: {doubt}")

    def _skills(self, c: _Context) -> None:
        by_category: dict[str, list[str]] = {}
        for skill in ranked_skills(c.ranked, c.request.role):
            by_category.setdefault(skill.category, []).append(skill.name)
        rows = [(category, by_category[category][:8]) for category in CATEGORY_ORDER if by_category.get(category)]
        professional = self._professional_skills(c)
        if professional:
            rows.append((PROFESSIONAL, professional))
        soft = [s.name for s in soft_signals(c.ranked).values()]
        if soft:
            rows.append(("Competencias", soft))
        c.doc.skills = rows
        if rows:
            c.trace("Habilidades", "habilidades y competencias", [f"raw/{r.candidate.entry.key}" for r in c.ranked])

    @staticmethod
    def _professional_skills(c: _Context) -> list[str]:
        """Habilidades del perfil de cada proyecto que no son tecnologías («Análisis de casos», «Planeación»)."""
        counts: Counter[str] = Counter()
        names: dict[str, str] = {}
        for r in c.ranked:
            for skill in (r.candidate.profile.skills if r.candidate.profile else []):
                if canonical(skill) or len(skill) > 40:
                    continue
                key = skill.strip().lower()
                names.setdefault(key, skill.strip()[:1].upper() + skill.strip()[1:])
                counts[key] += 1
        posting = c.request.role.posting
        wanted = " ".join(posting.technical + posting.responsibilities) if posting else ""
        ordered = sorted(counts, key=lambda k: (not (wanted and phrase_matches(k, wanted)), -counts[k], k))
        return [names[k] for k in ordered[:8]]

    def _education(self, c: _Context) -> None:
        degree, school, period = (c.contact.degree.strip(), c.contact.institution.strip(), c.contact.period.strip())
        if not (degree and school):
            c.note("Educación: escribe tu carrera y universidad (directo en el CV o en el paso 1 · Conectar).")
        courses = list(dict.fromkeys(pretty_course(r.candidate.entry.course_name) for r in c.ranked))[:4]
        c.doc.education = ResumeEducation(degree, school, period, courses)
