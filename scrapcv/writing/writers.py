"""Quién redacta cada sección del CV (Strategy + cadena de respaldo).

- `LlmResumeWriter`: redacta con cualquier `LanguageModel` (Ollama hoy, otro proveedor mañana).
- `RuleBasedResumeWriter`: texto armado con reglas a partir de la evidencia; nunca falla.
- `WriterChain`: prueba los escritores en orden y avisa si se usó uno que requiere revisión.

`ResumeBuilder` solo arma el documento; no sabe qué escritor respondió.
Agregar un proveedor de IA = otro `LanguageModel`; agregar otra estrategia = otro `ResumeWriter`.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, TypeVar

from scrapcv.analysis.guards import strip_numbers
from scrapcv.domain.skills import DATABASES, FRAMEWORKS, LANGUAGES, TOOLS, Skill, canonical
from scrapcv.ports import LanguageModel
from scrapcv.ranking.ranker import RankedProject
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.format import clean_title, is_generic_title, join_es, pretty_course
from scrapcv.writing.prompts import (
    COMPETENCIES_SYSTEM,
    PROJECT_SYSTEM,
    SUMMARY_SYSTEM,
    TIPS_SYSTEM,
    posting_context,
    project_context,
)
from scrapcv.writing.templates import ResumeTemplate

if TYPE_CHECKING:
    from scrapcv.ranking.match import MatchReport

log = logging.getLogger("scrapcv.resume")
T = TypeVar("T")


@dataclass(frozen=True)
class WritingRequest:
    """Todo lo que un escritor necesita saber del CV que se está armando."""

    template: ResumeTemplate
    role: JobRole
    ranked: list[RankedProject]
    degree: str = ""

    @property
    def target(self) -> str:
        return self.role.posting.title if self.role.posting else self.role.name


@dataclass(frozen=True)
class ProjectText:
    title: str
    bullets: list[str] = field(default_factory=list)


def _clean(text: object) -> str:
    cleaned = strip_numbers(str(text or "").strip())
    return cleaned[:1].upper() + cleaned[1:] if cleaned else ""


def ranked_skills(ranked: list[RankedProject], role: JobRole | None = None) -> list[Skill]:
    """Tecnologías con evidencia, primero las que pide el puesto y luego las más usadas."""
    weight: Counter[Skill] = Counter()
    for r in ranked:
        lines = {lang: stat.lines for lang, stat in r.candidate.facts.languages.items()}
        for skill in r.candidate.skills():
            weight[skill] += 1 + lines.get(skill.name, 0) / 1000
    wanted = role.keywords if role else frozenset()
    return sorted(weight, key=lambda s: (not (set(s.forms) & wanted), -weight[s], s.name))


# --- Contrato -------------------------------------------------------------------------------------

class ResumeWriter(ABC):
    """Redacta secciones. Devolver None significa «no pude»; la cadena prueba con el siguiente."""

    needs_review: bool = False  # True si el texto es de plantilla y el usuario debe personalizarlo

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def summary(self, request: WritingRequest) -> str | None: ...

    @abstractmethod
    def project(self, request: WritingRequest, ranked: RankedProject) -> ProjectText | None: ...

    @abstractmethod
    def competencies(self, request: WritingRequest) -> list[tuple[str, str]] | None: ...

    @abstractmethod
    def tips(self, request: WritingRequest, report: "MatchReport") -> list[str] | None: ...


# --- Con modelo de lenguaje ---------------------------------------------------------------------------

class LlmResumeWriter(ResumeWriter):
    def __init__(self, model: LanguageModel) -> None:
        self._model = model

    @property
    def name(self) -> str:
        return self._model.name

    def summary(self, request: WritingRequest) -> str | None:
        system = SUMMARY_SYSTEM.format(focus=request.template.intro_focus or "Escribe dos frases.")
        lines = [posting_context(request.role.posting) or f"Puesto objetivo: {request.role.name}"]
        if request.degree:
            lines.append(f"Carrera: {request.degree}")
        lines.append("Proyectos del estudiante:")
        lines += [project_context(r) for r in request.ranked]
        data = self._model.complete_json(system, "\n".join(lines) + "\n\nRedacta el texto.")
        return _clean(data.get("texto")) or None

    def project(self, request: WritingRequest, ranked: RankedProject) -> ProjectText | None:
        count = request.template.bullets_per_project
        prompt = "\n".join(filter(None, [posting_context(request.role.posting), project_context(ranked)]))
        data = self._model.complete_json(PROJECT_SYSTEM.format(count=count), prompt + "\n\nRedacta la entrada.")
        raw = data.get("vinetas")
        if isinstance(raw, str):
            raw = [raw]
        bullets = [b for b in (_clean(x) for x in raw) if b][:count] if isinstance(raw, list) else []
        if not bullets:
            return None
        title = _clean(data.get("titulo"))
        return ProjectText(title if 0 < len(title) <= 60 else _project_title(ranked.candidate.entry), bullets)

    def competencies(self, request: WritingRequest) -> list[tuple[str, str]] | None:
        prompt = "\n".join([posting_context(request.role.posting) or f"Puesto objetivo: {request.role.name}",
                            "Proyectos del estudiante:", *(project_context(r) for r in request.ranked)])
        data = self._model.complete_json(COMPETENCIES_SYSTEM, prompt + "\n\nAgrupa las competencias.")
        raw = data.get("competencias")
        items = []
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, dict) and (title := _clean(item.get("titulo"))):
                items.append((title, _clean(item.get("descripcion"))))
        return items[:5] or None

    def tips(self, request: WritingRequest, report: "MatchReport") -> list[str] | None:
        met = [f"{r.name} (en {join_es(list(r.projects[:2]))})" for r in report.strengths]
        missing = [f"{r.name} ({r.kind})" for r in report.gaps]
        prompt = "\n".join([
            posting_context(report.posting),
            "Requisitos que el CV demuestra: " + (", ".join(met) or "ninguno"),
            "Requisitos sin evidencia: " + (", ".join(missing) or "ninguno"),
            "Proyectos del CV: " + ", ".join(clean_title(r.candidate.entry.assignment_name) for r in request.ranked),
        ])
        data = self._model.complete_json(TIPS_SYSTEM, prompt + "\n\nDa los consejos.")
        raw = data.get("consejos")
        tips = [t for t in (_clean(x) for x in raw) if t] if isinstance(raw, list) else []
        return tips[:3] or None


# --- Sin modelo (respaldo) ------------------------------------------------------------------------------

_BACKEND = {"Node.js", "Express", "Flask", "Django", "FastAPI", "Spring Boot", ".NET", "Laravel", "API REST"}
_FRONTEND = {"React", "Vue", "Angular", "Svelte", "Next.js", "HTML", "CSS", "Tailwind CSS", "Bootstrap", "Figma"}
_DATA = {"Pandas", "NumPy", "scikit-learn", "TensorFlow", "PyTorch", "Jupyter", "Machine learning", "Matplotlib",
         "Seaborn", "Análisis de datos"}
_TESTING = {"pytest", "JUnit", "Jest", "Pruebas unitarias"}
_MARKUP = {"HTML", "CSS"}
_PERSISTENCE = {"SQLAlchemy", "Mongoose"}


class RuleBasedResumeWriter(ResumeWriter):
    """Texto armado con la evidencia, sin inventar nada. El usuario debe personalizarlo."""

    needs_review = True

    @property
    def name(self) -> str:
        return "reglas"

    def summary(self, request: WritingRequest) -> str:
        ordered = [s for s in ranked_skills(request.ranked, request.role) if s.name not in _TESTING]
        langs = [s.name for s in ordered if s.category == LANGUAGES][:2]
        others = [s.name for s in ordered if s.category in (FRAMEWORKS, DATABASES, TOOLS)][:2]
        skills = (langs + others) or _profile_skills(request.ranked)[:3]
        who = f"Estudiante de {request.degree}" if request.degree else "Estudiante universitario"
        team = ", incluido trabajo en equipo" if any(r.candidate.entry.is_group for r in request.ranked) else ""
        if skills:
            practice = join_es([_lower_first(s) for s in skills])
            first = f"{who} con experiencia práctica en {practice}, adquirida en proyectos académicos{team}."
        else:
            first = f"{who} con proyectos académicos relacionados con el puesto{team}."
        if request.template.key == "practicas":
            return f"{first} Busca realizar prácticas profesionales como {request.target} para aportar y seguir creciendo."
        return f"{first} Busca aportar como {request.target}."

    def project(self, request: WritingRequest, ranked: RankedProject) -> ProjectText:
        candidate = ranked.candidate
        facts, profile, entry = candidate.facts, candidate.profile, candidate.entry
        skills = candidate.skills()
        names = {s.name for s in skills}
        langs = [s.name for s in skills if s.category == LANGUAGES]
        code_langs = [lang for lang in langs if lang not in _MARKUP] or langs
        libs = [s.name for s in skills if s.category == FRAMEWORKS and s.name not in _TESTING | _PERSISTENCE]
        stores = [s.name for s in skills if s.category == DATABASES or s.name in _PERSISTENCE]
        tests = [s.name for s in skills if s.name in _TESTING]
        tech = join_es((code_langs[:2] + libs[:2]) or stores[:2])
        bullets: list[str] = []
        if profile and profile.summary and profile.origin != "estatico":
            bullets += [s.strip().rstrip(".") + "." for s in profile.summary.split(". ") if s.strip()]
        if names & _BACKEND:
            bullets.append(f"Desarrolló la lógica del servidor con {tech}.")
        elif names & _DATA:
            bullets.append(f"Analizó y modeló datos con {tech}.")
        elif names & _FRONTEND:
            bullets.append(f"Construyó la interfaz de usuario con {join_es((langs[:3] + libs[:2]))}.")
        elif langs:
            bullets.append(f"Programó la solución en {join_es(langs[:3])}" + (f" con {join_es(libs[:2])}." if libs else "."))
        if stores:
            bullets.append(f"Implementó la persistencia de datos con {join_es(stores[:2])}.")
        if tests:
            bullets.append(f"Escribió pruebas automatizadas con {join_es(tests)}.")
        kinds = {d.kind for d in facts.documents}
        if not langs:
            if kinds & {"pdf", "docx", "texto"} and not bullets:
                bullets.append("Elaboró un reporte escrito con el análisis, la propuesta y las conclusiones del proyecto.")
            if "pptx" in kinds:
                bullets.append("Preparó y presentó los resultados en una presentación ejecutiva.")
            if "xlsx" in kinds or "csv" in kinds:
                bullets.append("Organizó y analizó la información en hojas de cálculo.")
            if any(link.kind == "figma" for link in facts.links):
                bullets.append("Diseñó un prototipo interactivo en Figma.")
            if any(link.kind == "youtube" for link in facts.links):
                bullets.append("Produjo un video para presentar el proyecto.")
        elif kinds & {"pdf", "docx", "pptx"}:
            bullets.append("Documentó el diseño y los resultados del proyecto.")
        if any(link.kind == "repositorio" for link in facts.links):
            bullets.append("Versionó el código en un repositorio Git público.")
        if entry.is_group:
            bullets.append("Colaboró con su equipo en el diseño, la integración y la entrega.")
        if profile and profile.skills:
            bullets.append(f"Aplicó {join_es([_lower_first(s) for s in profile.skills[:3]])}.")
        return ProjectText(_project_title(entry), list(dict.fromkeys(bullets))[: request.template.bullets_per_project])

    def competencies(self, request: WritingRequest) -> list[tuple[str, str]]:
        groups: dict[str, list[str]] = {}
        for r in request.ranked:
            title = clean_title(r.candidate.entry.assignment_name)
            names = {s.name for s in r.candidate.skills()}
            for label, family in (("Desarrollo backend", _BACKEND), ("Desarrollo frontend", _FRONTEND),
                                  ("Ciencia de datos", _DATA)):
                if names & family:
                    groups.setdefault(label, []).append(title)
        if not groups:
            names = [s.name for s in ranked_skills(request.ranked, request.role)][:4] or _profile_skills(request.ranked)[:4]
            out = []
            for name in names:
                used = [clean_title(r.candidate.entry.assignment_name) for r in request.ranked
                        if name.lower() in r.candidate.corpus() or name in (r.candidate.profile.skills if r.candidate.profile else [])]
                out.append((name, f"Aplicado en {join_es(used[:2])}." if used else ""))
            return out
        return [(label, f"Aplicado en {join_es(titles[:3])}.") for label, titles in groups.items()]

    def tips(self, request: WritingRequest, report: "MatchReport") -> list[str]:
        tips: list[str] = []
        for gap in report.gaps:
            if gap.elsewhere:
                tips.append(f"Ya demostraste «{gap.name}» en «{gap.elsewhere[0]}», pero no quedó en el CV: "
                            "sube el «Máximo de proyectos» en Más opciones.")
        missing = [g.name for g in report.gaps if g.kind == "indispensable" and not g.elsewhere]
        if missing:
            tips.append(f"La vacante pide {join_es(missing[:4])} y no aparece en tus entregas. Si lo has hecho fuera de "
                        "clase (trabajo, voluntariado, cursos), agrégalo al CV como un proyecto más; si no, es un buen "
                        "siguiente aprendizaje.")
        top = [s.name for s in report.strengths if s.kind != "blanda"][:3]
        if top:
            tips.append(f"Abre tu perfil profesional con {join_es(top)}: es lo primero que el reclutador busca en esta vacante.")
        if report.posting.other:
            tips.append("Menciona en tu carta o en el perfil que cumples: " + "; ".join(report.posting.other[:3]) + ".")
        return tips[:4]


def _project_title(entry) -> str:
    """Título legible; si la tarea se llama «Entrega final del proyecto», se usa la materia."""
    if is_generic_title(entry.assignment_name):
        return f"Proyecto de {pretty_course(entry.course_name)}"
    return clean_title(entry.assignment_name)


def _lower_first(text: str) -> str:
    """«Análisis de casos» → «análisis de casos», pero respeta siglas y nombres («Python», «SQL»)."""
    first = text.split(" ", 1)[0]
    if canonical(text) or first.isupper() or (len(first) > 1 and any(ch.isupper() for ch in first[1:])):
        return text
    return text[:1].lower() + text[1:]


def _profile_skills(ranked: list[RankedProject]) -> list[str]:
    counts: Counter[str] = Counter()
    for r in ranked:
        for skill in (r.candidate.profile.skills if r.candidate.profile else []):
            if not canonical(skill):
                counts[skill.strip()] += 1
    return [s for s, _ in counts.most_common()]


# --- Cadena -----------------------------------------------------------------------------------------------

class WriterChain:
    """Prueba cada escritor en orden; el primero que responde gana."""

    def __init__(self, writers: list[ResumeWriter]) -> None:
        if not writers:
            raise ValueError("Se necesita al menos un escritor.")
        self._writers = writers

    @property
    def name(self) -> str:
        return self._writers[0].name

    def write(self, section: str, call: Callable[[ResumeWriter], T | None]) -> tuple[T | None, str | None]:
        """Devuelve (texto, aviso para el usuario o None)."""
        for writer in self._writers:
            try:
                value = call(writer)
            except Exception as exc:  # el modelo puede fallar de muchas formas; nunca detiene el CV
                log.warning("%s con %s falló: %s", section, writer.name, exc.__class__.__name__)
                continue
            if value:
                note = f"{section}: redactado sin modelo de lenguaje; personalízalo con tus palabras." if writer.needs_review else None
                return value, note
        return None, None
