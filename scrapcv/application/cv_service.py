"""Etapa 4 y 5: ranking por puesto y redacción del CV (CAR-22 a CAR-27)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scrapcv.domain.models import ContactInfo, Stage, StageStatus, UserInfo
from scrapcv.ports import AnalysisStore, CvRepository, IndexRepository, UserRepository
from scrapcv.ranking.ranker import ProjectCandidate, RankedProject, SelectionCriteria, WeightedRanker
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.cv import CvComposer, CvRenderer
from scrapcv.writing.resume import ResumeBuilder, ResumeWriter, template_by_key

_USABLE = (StageStatus.OK, StageStatus.PARTIAL)
EVIDENCE_KEY = "evidencia"  # formato original: borrador con la evidencia visible en cada viñeta


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
        resume: ResumeBuilder | None = None,
        contact: ContactInfo | None = None,
    ) -> None:
        self._resume = resume or ResumeBuilder(ResumeWriter(None))
        self._contact = contact or ContactInfo()
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

    def generate(self, role: JobRole, criteria: SelectionCriteria, template_key: str = EVIDENCE_KEY) -> CvResult:
        ranked = self.ranking(role, criteria)
        user = self._users.load() or UserInfo(0, "Tu nombre")
        template = template_by_key(template_key)
        if template is None:  # borrador con evidencia por viñeta (formato original)
            markdown = self._renderer.render(self._composer.compose(user, role, ranked))
        else:
            markdown = self._resume.build(user, self._contact, role, template, ranked)
        return CvResult(markdown, ranked, self._repository.save_draft(self._slug(role, template_key), markdown))

    @staticmethod
    def _slug(role: JobRole, template_key: str) -> str:
        return role.slug if template_key == EVIDENCE_KEY else f"{role.slug}_{template_key}"

    def save_edit(self, role: JobRole, markdown: str, template_key: str = EVIDENCE_KEY) -> Path:
        """CAR-27: el usuario edita el borrador."""
        return self._repository.save_draft(self._slug(role, template_key), markdown)

    def approve(self, role: JobRole, markdown: str, template_key: str = EVIDENCE_KEY) -> Path:
        """CAR-27: el usuario aprueba; solo entonces existe un CV final."""
        return self._repository.save_final(self._slug(role, template_key), markdown)
