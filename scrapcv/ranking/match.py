"""Qué tanto cubre el CV lo que pide la vacante (equivalente al «Match %» de Resume Optimizer).

El porcentaje se calcula con la evidencia, no lo escribe el modelo: cada requisito
cuenta si alguna entrega del CV lo demuestra. Los indispensables pesan el doble.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from scrapcv.analysis.signals import soft_signals
from scrapcv.domain.posting import JobPosting
from scrapcv.domain.skills import canonical, normalize
from scrapcv.domain.text import phrase_matches
from scrapcv.ranking.ranker import ProjectCandidate, RankedProject, RoleAffinityScorer

REQUIRED, PREFERRED, SOFT = "indispensable", "deseable", "blanda"
_WEIGHTS = {REQUIRED: 1.0, PREFERRED: 0.5, SOFT: 0.5}


@dataclass(frozen=True)
class RequirementStatus:
    name: str
    kind: str
    projects: tuple[str, ...] = ()  # entregas del CV que lo demuestran
    elsewhere: tuple[str, ...] = ()  # entregas con evidencia que no quedaron en el CV

    @property
    def met(self) -> bool:
        return bool(self.projects)


@dataclass
class MatchReport:
    posting: JobPosting
    percentage: int
    requirements: list[RequirementStatus]
    tips: list[str] = field(default_factory=list)

    @property
    def strengths(self) -> list[RequirementStatus]:
        return [r for r in self.requirements if r.met]

    @property
    def gaps(self) -> list[RequirementStatus]:
        return [r for r in self.requirements if not r.met]


def _title(candidate: ProjectCandidate) -> str:
    return candidate.entry.assignment_name


class MatchAnalyzer:
    def analyze(self, posting: JobPosting, ranked: list[RankedProject], others: list[ProjectCandidate]) -> MatchReport:
        selected = [r.candidate for r in ranked]
        selected_keys = {c.entry.key for c in selected}
        rest = [c for c in others if c.entry.key not in selected_keys]
        requirements = [
            *(self._technical(name, REQUIRED, selected, rest) for name in posting.required),
            *(self._technical(name, PREFERRED, selected, rest) for name in posting.preferred),
            *self._soft(posting, ranked),
        ]
        total = sum(_WEIGHTS[r.kind] for r in requirements)
        met = sum(_WEIGHTS[r.kind] for r in requirements if r.met)
        percentage = round(100 * met / total) if total else 0
        return MatchReport(posting, percentage, requirements)

    def _technical(self, name: str, kind: str, selected: list[ProjectCandidate], rest: list[ProjectCandidate]) -> RequirementStatus:
        skill = canonical(name)
        forms = skill.forms if skill else (normalize(name),)

        def shows(candidate: ProjectCandidate) -> bool:
            if skill and skill in candidate.skills():
                return True
            corpus, tokens = candidate.corpus(), candidate.tokens()
            if not skill:
                return phrase_matches(name, corpus)
            return any(RoleAffinityScorer._matches(form, corpus, tokens) for form in forms)

        return RequirementStatus(
            name, kind,
            tuple(_title(c) for c in selected if shows(c)),
            tuple(_title(c) for c in rest if shows(c))[:3],
        )

    @staticmethod
    def _soft(posting: JobPosting, ranked: list[RankedProject]) -> list[RequirementStatus]:
        signals = {normalize(s.name): s for s in soft_signals(ranked).values()}
        titles = {r.candidate.entry.key: _title(r.candidate) for r in ranked}
        out = []
        for name in posting.soft_skills:
            signal = signals.get(normalize(name))
            projects = tuple(titles[k] for k in dict.fromkeys(signal.projects) if k in titles) if signal else ()
            out.append(RequirementStatus(name, SOFT, projects))
        return out
