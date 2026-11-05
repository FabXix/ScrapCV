"""Redacción del CV (CAR-25) con rastreabilidad (CAR-26).

`CvComposer` decide QUÉ dice el CV (modelo `CvDocument`); `CvRenderer`
decide CÓMO se ve. Así, exportar a otro formato (fase 4) es solo otro
renderer. Las cifras salen de `Facts` o de Canvas, nunca del modelo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from scrapcv.domain.facts import Facts
from scrapcv.domain.models import UserInfo
from scrapcv.ranking.ranker import RankedProject
from scrapcv.ranking.roles import JobRole

_DOC_UNITS = {"pdf": "páginas", "pptx": "diapositivas", "ipynb": "celdas", "docx": "párrafos"}
_DOC_NAMES = {"pdf": "PDF", "pptx": "presentación", "ipynb": "notebook", "docx": "documento Word", "texto": "texto"}


@dataclass(frozen=True)
class CvBullet:
    text: str
    evidence: tuple[str, ...]  # rutas relativas a data/raw/<materia>/<tarea>/


@dataclass
class CvProject:
    key: str
    title: str
    course: str
    submitted_at: str
    is_group: bool
    bullets: list[CvBullet] = field(default_factory=list)
    doubtful: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class CvDocument:
    user: UserInfo
    role: JobRole
    projects: list[CvProject]
    skills: list[CvBullet]
    generated_on: str


class FactsPhraser:
    """Convierte hechos en frases. Única fuente de cifras del CV."""

    def code_line(self, facts: Facts) -> str | None:
        if not facts.languages:
            return None
        parts = [
            f"{stat.lines} líneas en {lang} ({stat.files} archivo{'s' if stat.files != 1 else ''})"
            for lang, stat in sorted(facts.languages.items(), key=lambda kv: -kv[1].lines)
        ]
        return "Código entregado: " + "; ".join(parts) + "."

    def documents_line(self, facts: Facts) -> str | None:
        docs = [d for d in facts.documents if d.kind in _DOC_UNITS]
        if not docs:
            return None
        parts = [f"{_DOC_NAMES[d.kind]} de {d.units} {_DOC_UNITS[d.kind]}" for d in docs]
        return "Documentación entregada: " + ", ".join(parts) + "."

    def dependencies_line(self, facts: Facts) -> str | None:
        if not facts.dependencies:
            return None
        return "Dependencias declaradas: " + ", ".join(facts.dependencies[:10]) + "."

    @staticmethod
    def grade_line(score: float | None, points: float | None) -> str | None:
        if score is None or not points:
            return None
        return f"Calificación obtenida: {score:g}/{points:g}."


class CvComposer:
    def __init__(self, phraser: FactsPhraser | None = None) -> None:
        self._phraser = phraser or FactsPhraser()

    def compose(self, user: UserInfo, role: JobRole, ranked: list[RankedProject]) -> CvDocument:
        projects = [self._project(r) for r in ranked]
        return CvDocument(user, role, projects, self._skills(ranked), date.today().isoformat())

    def _project(self, ranked: RankedProject) -> CvProject:
        entry, facts, profile = ranked.candidate.entry, ranked.candidate.facts, ranked.candidate.profile
        project = CvProject(entry.key, entry.assignment_name, entry.course_name, entry.submitted_at[:10],
                            entry.is_group, score=ranked.total)
        code_files = tuple(facts.code_files[:3])
        dep_files = tuple(facts.dependency_files[:3])
        doc_files = tuple(d.path for d in facts.documents if d.kind in _DOC_UNITS)[:3]
        any_files = tuple(facts.evidence_files[:3])

        if profile and profile.summary:
            project.bullets.append(CvBullet(profile.summary, tuple(profile.sources[:3]) or any_files))
        technologies = (profile.technologies if profile else []) or sorted(facts.languages)
        if technologies:
            tech_files = (dep_files + code_files[:1]) or any_files
            project.bullets.append(CvBullet("Tecnologías: " + ", ".join(dict.fromkeys(technologies)) + ".", tech_files))
        for line, files in (
            (self._phraser.code_line(facts), code_files),
            (self._phraser.documents_line(facts), doc_files),
            (self._phraser.dependencies_line(facts), dep_files),
        ):
            if line and files:
                project.bullets.append(CvBullet(line, files))
        grade = self._phraser.grade_line(entry.score, entry.points_possible)
        if grade:
            project.bullets.append(CvBullet(grade, ("submission.json",)))
        for link in facts.links:
            if link.kind in ("repositorio", "figma", "youtube", "drive"):
                project.bullets.append(CvBullet(f"Enlace ({link.kind}): {link.url}", ("enlaces / texto en línea",)))
        if profile:
            project.doubtful = list(profile.doubtful)
        return project

    @staticmethod
    def _skills(ranked: list[RankedProject]) -> list[CvBullet]:
        lines: Counter[str] = Counter()
        projects: dict[str, list[str]] = {}
        for r in ranked:
            for lang, stat in r.candidate.facts.languages.items():
                lines[lang] += stat.lines
                projects.setdefault(lang, []).append(r.candidate.entry.key)
        return [
            CvBullet(f"{lang}: {total} líneas en {len(projects[lang])} entrega(s).", tuple(projects[lang]))
            for lang, total in lines.most_common()
        ]


class CvRenderer(ABC):
    @abstractmethod
    def render(self, document: CvDocument) -> str: ...


class MarkdownCvRenderer(CvRenderer):
    def render(self, document: CvDocument) -> str:
        user = document.user
        out = [f"# {user.name or 'Tu nombre'}", ""]
        if user.email:
            out += [user.email, ""]
        out += [
            f"**Puesto objetivo:** {document.role.name}  ",
            f"*Borrador generado por ScrapCV el {document.generated_on}. Cada línea indica la evidencia que la respalda; "
            "revísalo y edítalo antes de enviarlo.*",
            "",
            "## Proyectos académicos",
            "",
        ]
        if not document.projects:
            out += ["_No se encontraron proyectos afines a este puesto con los filtros elegidos._", ""]
        for project in document.projects:
            tag = " · **[Proyecto en equipo]**" if project.is_group else ""
            out.append(f"### {project.title}")
            out.append(f"*{project.course}* · {project.submitted_at or 'sin fecha'}{tag}")
            out.append("")
            for bullet in project.bullets:
                out.append(f"- {bullet.text} {self._evidence(project.key, bullet)}")
            for note in project.doubtful:
                out.append(f"  - ⚠ **Verificar:** {note}")
            out.append("")
        if document.skills:
            out += ["## Lenguajes con evidencia", ""]
            for bullet in document.skills:
                out.append(f"- {bullet.text} <sub>Evidencia: {', '.join(bullet.evidence)}</sub>")
            out.append("")
        return "\n".join(out)

    @staticmethod
    def _evidence(key: str, bullet: CvBullet) -> str:
        files = "; ".join(f"`{f}`" for f in bullet.evidence)
        return f"<sub>Evidencia: raw/{key} → {files}</sub>"


def untraceable_bullets(document: CvDocument) -> list[CvBullet]:
    """Viñetas sin evidencia (debe ser una lista vacía; sección 7.1 Rastreabilidad)."""
    return [b for p in document.projects for b in p.bullets if not b.evidence]
