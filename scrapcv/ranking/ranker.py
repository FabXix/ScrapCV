"""Ranking de proyectos (CAR-23) y filtros del usuario (CAR-24).

Cada criterio es una estrategia (`ProjectScorer`); el ranker las combina con
pesos. Un criterio nuevo es una clase nueva, sin tocar el ranker (OCP).
"""
from __future__ import annotations

import math
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from scrapcv.domain.facts import Facts, ProjectProfile
from scrapcv.domain.models import IndexEntry
from scrapcv.domain.text import tokenize
from scrapcv.ranking.roles import JobRole


@dataclass(frozen=True)
class ProjectCandidate:
    entry: IndexEntry
    facts: Facts
    profile: ProjectProfile | None = None

    def corpus(self) -> str:
        parts = [self.entry.assignment_name, self.entry.course_name, *self.facts.languages, *self.facts.dependencies]
        parts += [doc.kind for doc in self.facts.documents]
        if self.profile:
            parts += [self.profile.summary, self.profile.scope, *self.profile.technologies, *self.profile.skills]
        text = " ".join(parts).lower()
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()

    def tokens(self) -> set[str]:
        # Los lenguajes de una letra (C, R) no sobreviven a tokenize(); se agregan aparte.
        return tokenize(self.corpus()) | {lang.lower() for lang in self.facts.languages}


@dataclass(frozen=True)
class ScoreDetail:
    value: float  # 0..1
    note: str = ""


class ProjectScorer(ABC):
    name: str = ""

    @abstractmethod
    def score(self, candidate: ProjectCandidate, role: JobRole) -> ScoreDetail: ...


class RoleAffinityScorer(ProjectScorer):
    """Qué tanto coinciden las palabras clave del puesto con la evidencia."""

    name = "afinidad"

    def __init__(self, saturation: int = 5) -> None:
        self._saturation = saturation

    def score(self, candidate: ProjectCandidate, role: JobRole) -> ScoreDetail:
        corpus = candidate.corpus()
        tokens = candidate.tokens()
        matched = sorted(k for k in role.keywords if self._matches(k, corpus, tokens))
        value = min(1.0, len(matched) / max(1, min(self._saturation, len(role.keywords))))
        return ScoreDetail(value, ", ".join(matched[:8]))

    @staticmethod
    def _matches(keyword: str, corpus: str, tokens: set[str]) -> bool:
        normalized = unicodedata.normalize("NFKD", keyword).encode("ascii", "ignore").decode().lower()
        return normalized in corpus if " " in normalized else normalized in tokens


class SizeScorer(ProjectScorer):
    """Tamaño de la evidencia, en escala logarítmica para no premiar solo el volumen."""

    name = "tamaño"

    def __init__(self, reference_units: int = 3000) -> None:
        self._reference = reference_units

    def score(self, candidate: ProjectCandidate, role: JobRole) -> ScoreDetail:
        units = candidate.facts.total_code_lines + candidate.facts.document_chars / 60
        return ScoreDetail(min(1.0, math.log10(1 + units) / math.log10(1 + self._reference)))


class GradeScorer(ProjectScorer):
    name = "calificación"

    def score(self, candidate: ProjectCandidate, role: JobRole) -> ScoreDetail:
        ratio = candidate.entry.grade_ratio
        return ScoreDetail(0.5, "sin calificación") if ratio is None else ScoreDetail(ratio)


@dataclass(frozen=True)
class RankedProject:
    candidate: ProjectCandidate
    total: float
    breakdown: dict[str, ScoreDetail]

    @property
    def affinity(self) -> float:
        return self.breakdown.get(RoleAffinityScorer.name, ScoreDetail(0)).value


@dataclass(frozen=True)
class SelectionCriteria:
    """Filtros del usuario (CAR-24)."""

    include_courses: frozenset[str] = frozenset()
    exclude_courses: frozenset[str] = frozenset()
    max_projects: int = 5
    min_affinity: float = 0.01

    def admits(self, candidate: ProjectCandidate) -> bool:
        course = candidate.entry.course_name
        if self.include_courses and course not in self.include_courses:
            return False
        return course not in self.exclude_courses


@dataclass
class WeightedRanker:
    scorers: list[tuple[ProjectScorer, float]] = field(default_factory=lambda: [
        (RoleAffinityScorer(), 0.6), (SizeScorer(), 0.2), (GradeScorer(), 0.2),
    ])

    def rank(self, candidates: list[ProjectCandidate], role: JobRole) -> list[RankedProject]:
        total_weight = sum(weight for _, weight in self.scorers) or 1.0
        ranked = []
        for candidate in candidates:
            breakdown = {scorer.name: scorer.score(candidate, role) for scorer, _ in self.scorers}
            total = sum(breakdown[s.name].value * w for s, w in self.scorers) / total_weight
            ranked.append(RankedProject(candidate, round(total, 4), breakdown))
        return sorted(ranked, key=lambda r: (-r.total, r.candidate.entry.key))

    def select(self, candidates: list[ProjectCandidate], role: JobRole, criteria: SelectionCriteria) -> list[RankedProject]:
        admitted = [c for c in candidates if criteria.admits(c)]
        ranked = [r for r in self.rank(admitted, role) if r.affinity >= criteria.min_affinity]
        return ranked[: max(0, criteria.max_projects)]
