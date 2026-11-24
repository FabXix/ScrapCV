"""Etapa 4 y 5: ranking por puesto o vacante, redacción del CV y exportación (CAR-22 a CAR-27)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scrapcv.application.advice import CvAdvisor
from scrapcv.domain.models import ContactInfo, Stage, StageStatus, UserInfo
from scrapcv.ports import (AnalysisStore, CvExporter, CvRepository, IndexRepository, NullProgress, ProgressListener,
                           UserRepository)
from scrapcv.ranking.match import MatchReport
from scrapcv.ranking.ranker import ProjectCandidate, RankedProject, SelectionCriteria, WeightedRanker
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.cv import CvComposer, CvRenderer
from scrapcv.writing.resume import ResumeBuilder, template_by_key
from scrapcv.writing.writers import WritingRequest

_USABLE = (StageStatus.OK, StageStatus.PARTIAL)
EVIDENCE_KEY = "evidencia"  # formato original: borrador con la evidencia visible en cada viñeta


@dataclass(frozen=True)
class CvResult:
    markdown: str
    ranked: list[RankedProject]
    path: Path
    review: list[str] = field(default_factory=list)
    report: MatchReport | None = None
    role: JobRole | None = None  # el puesto con que se generó (la interfaz lo necesita para guardar y exportar)


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
        resume: ResumeBuilder,
        advisor: CvAdvisor | None = None,
        contact: ContactInfo | None = None,
        exporters: tuple[CvExporter, ...] = (),
    ) -> None:
        self._index = index
        self._store = store
        self._users = users
        self._ranker = ranker
        self._composer = composer
        self._renderer = renderer
        self._repository = repository
        self._resume = resume
        self._advisor = advisor
        self._contact = contact or ContactInfo()
        self._exporters = {e.key: e for e in exporters}

    def candidates(self) -> list[ProjectCandidate]:
        result = []
        for entry in self._index.all():
            if entry.stage(Stage.EXTRACT).status not in _USABLE:
                continue
            facts = self._store.load_facts(entry.key)
            if facts is not None:
                result.append(ProjectCandidate(entry, facts, self._store.load_profile(entry.key)))
        return result

    def eligible_count(self) -> int:
        return sum(1 for c in self.candidates() if self._ranker.eligible(c))

    def ranking(self, role: JobRole, criteria: SelectionCriteria) -> list[RankedProject]:
        return self._ranker.select(self.candidates(), role, criteria)

    def generate(self, role: JobRole, criteria: SelectionCriteria, template_key: str = EVIDENCE_KEY,
                 progress: ProgressListener | None = None) -> CvResult:
        progress = progress or NullProgress()
        progress.info("Eligiendo los proyectos que mejor encajan…")
        candidates = self.candidates()
        ranked = self._ranker.select(candidates, role, criteria)
        user = self._users.load() or UserInfo(0, "Tu nombre")
        template = template_by_key(template_key)
        slug = self._slug(role, template_key)
        if template is None:  # borrador con evidencia por viñeta (formato original)
            markdown = self._renderer.render(self._composer.compose(user, role, ranked))
            return CvResult(markdown, ranked, self._repository.save_draft(slug, markdown), role=role)
        draft = self._resume.build(user, self._contact, role, template, ranked, progress)
        self._repository.save_evidence(slug, draft.evidence)
        eligible = [c for c in candidates if self._ranker.eligible(c)]
        request = WritingRequest(template, role, ranked, self._contact.degree)
        if self._advisor and role.posting:
            progress.info("Comparando tu CV con la vacante…")
        report = self._advisor.advise(request, eligible) if self._advisor else None
        if report and report.posting.other:
            draft.review.append("La vacante también pide: " + "; ".join(report.posting.other) + ". Confirma que lo cumples.")
        return CvResult(draft.markdown, ranked, self._repository.save_draft(slug, draft.markdown), draft.review, report, role)

    @staticmethod
    def _slug(role: JobRole, template_key: str) -> str:
        return role.slug if template_key == EVIDENCE_KEY else f"{role.slug}_{template_key}"

    def save_edit(self, role: JobRole, markdown: str, template_key: str = EVIDENCE_KEY) -> Path:
        """CAR-27: el usuario edita el borrador."""
        return self._repository.save_draft(self._slug(role, template_key), markdown)

    def approve(self, role: JobRole, markdown: str, template_key: str = EVIDENCE_KEY) -> Path:
        """CAR-27: el usuario aprueba; solo entonces existe un CV final."""
        return self._repository.save_final(self._slug(role, template_key), markdown)

    # --- Exportación -------------------------------------------------------------------------------
    def export_formats(self) -> list[tuple[str, str]]:
        return [(e.key, e.label) for e in self._exporters.values()]

    def export(self, role: JobRole, markdown: str, template_key: str, fmt: str) -> Path:
        exporter = self._exporters.get(fmt)
        if exporter is None:
            raise ValueError(f"Formato de exportación desconocido: {fmt}")
        return self._repository.save_export(self._slug(role, template_key), exporter.extension, exporter.export(markdown))
