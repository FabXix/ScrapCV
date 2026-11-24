"""¿Esta entrega puede presentarse como proyecto en un CV?

Un quiz, un examen o un foro no son proyectos aunque tengan afinidad con el
puesto. Cada regla es un `CandidateFilter`; una regla nueva es una clase nueva.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from scrapcv.domain.skills import normalize

if TYPE_CHECKING:
    from scrapcv.ranking.ranker import ProjectCandidate

_ASSESSMENT = re.compile(
    r"\b(quiz+|examen(es)?|exam|evaluacion|autoevaluacion|coevaluacion|encuesta|foro|asistencia|cuestionario|"
    r"reflexion|diagnostico|lectura|participacion|bitacora|asesoria)\b"
)


class CandidateFilter(ABC):
    @abstractmethod
    def rejects(self, candidate: "ProjectCandidate") -> str | None:
        """Motivo por el que la entrega no va al CV, o None si se admite."""


class AssessmentFilter(CandidateFilter):
    """Quizzes, exámenes, foros, reflexiones…: evaluaciones, no proyectos."""

    def rejects(self, candidate: "ProjectCandidate") -> str | None:
        if _ASSESSMENT.search(normalize(candidate.entry.assignment_name)):
            return "es una evaluación o actividad de clase, no un proyecto"
        return None


class EvidenceFilter(CandidateFilter):
    """Sin código, documento legible ni repositorio no hay nada que mostrar."""

    def rejects(self, candidate: "ProjectCandidate") -> str | None:
        facts = candidate.facts
        has_repo = any(link.kind == "repositorio" for link in facts.links)
        if facts.has_readable_content or has_repo:
            return None
        return "no tiene código, documento legible ni repositorio"


DEFAULT_FILTERS: tuple[CandidateFilter, ...] = (AssessmentFilter(), EvidenceFilter())
