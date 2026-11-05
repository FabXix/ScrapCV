"""Etapa 4 y 5: ranking por puesto y redacción del CV (CAR-22 a CAR-27)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scrapcv.domain.models import Stage, StageStatus, UserInfo
from scrapcv.ports import AnalysisStore, CvRepository, IndexRepository, UserRepository
from scrapcv.ranking.ranker import ProjectCandidate, RankedProject, SelectionCriteria, WeightedRanker
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.cv import CvComposer, CvRenderer

_USABLE = (StageStatus.OK, StageStatus.PARTIAL)


@dataclass(frozen=True)
class CvResult:
    markdown: str
    ranked: list[RankedProject]
    path: Path


class CvService:
    def __init__(
        self,
        index: IndexRepository,
        store: AnalysisStore,
        users: UserRepository,
        ranker: WeightedRanker,
        composer: CvComposer,
        renderer: CvRenderer,
        repository: CvRepository,
    ) -> None:
        self._index = index
        self._store = store
        self._users = users
        self._ranker = ranker
        self._composer = composer
        self._renderer = renderer
        self._repository = repository

    def candidates(self) -> list[ProjectCandidate]:
        result = []
        for entry in self._index.all():
            if entry.stage(Stage.EXTRACT).status not in _USABLE:
                continue
            facts = self._store.load_facts(entry.key)
            if facts is not None:
                result.append(ProjectCandidate(entry, facts, self._store.load_profile(entry.key)))
        return result

    def ranking(self, role: JobRole, criteria: SelectionCriteria) -> list[RankedProject]:
        return self._ranker.select(self.candidates(), role, criteria)

    def generate(self, role: JobRole, criteria: SelectionCriteria) -> CvResult:
        ranked = self.ranking(role, criteria)
        user = self._users.load() or UserInfo(0, "Tu nombre")
        markdown = self._renderer.render(self._composer.compose(user, role, ranked))
        return CvResult(markdown, ranked, self._repository.save_draft(role.slug, markdown))

    def save_edit(self, role: JobRole, markdown: str) -> Path:
        """CAR-27: el usuario edita el borrador."""
        return self._repository.save_draft(role.slug, markdown)

    def approve(self, role: JobRole, markdown: str) -> Path:
        """CAR-27: el usuario aprueba; solo entonces existe un CV final."""
        return self._repository.save_final(role.slug, markdown)
