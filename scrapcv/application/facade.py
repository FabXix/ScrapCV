"""Fachada de la aplicación: lo único que la interfaz gráfica conoce.

La interfaz no sabe de Canvas, Ollama ni del disco; solo pide "ingesta",
"extrae", "perfila" o "genera el CV" (Facade + DIP).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scrapcv.application.analysis import ExtractionService, ProfileService, StageSummary
from scrapcv.application.cv_revision import CvReviser, RevisionRejected
from scrapcv.application.cv_service import CvResult, CvService
from scrapcv.application.ingest import IngestService, IngestSummary
from scrapcv.domain.facts import Facts, ProjectProfile
from scrapcv.domain.models import IndexEntry
from scrapcv.ports import AnalysisStore, CanvasReader, IndexRepository, NullProgress, ProgressListener
from scrapcv.ranking.ranker import RankedProject, SelectionCriteria
from scrapcv.ranking.roles import JobRole, RoleCatalog


@dataclass(frozen=True)
class PipelineSummary:
    ingest: IngestSummary
    extraction: StageSummary
    profiles: StageSummary


class ScrapCvFacade:
    def __init__(
        self,
        reader: CanvasReader,
        ingest: IngestService,
        extraction: ExtractionService,
        profiles: ProfileService,
        cv: CvService,
        index: IndexRepository,
        store: AnalysisStore,
        roles: RoleCatalog,
        data_dir: Path,
        profiler_name: str,
        reviser: CvReviser | None = None,
    ) -> None:
        self._reviser = reviser
        self._reader = reader
        self._ingest = ingest
        self._extraction = extraction
        self._profiles = profiles
        self._cv = cv
        self._index = index
        self._store = store
        self.roles = roles
        self.data_dir = data_dir
        self.profiler_name = profiler_name

    # --- Etapas ------------------------------------------------------------------
    def check_connection(self) -> str:
        return self._reader.current_user().name

    def ingest(self, progress: ProgressListener = NullProgress()) -> IngestSummary:
        return self._ingest.run(progress)

    def extract(self, progress: ProgressListener = NullProgress()) -> StageSummary:
        return self._extraction.run(progress)

    def build_profiles(self, progress: ProgressListener = NullProgress()) -> StageSummary:
        return self._profiles.run(progress)

    def run_all(self, progress: ProgressListener = NullProgress()) -> PipelineSummary:
        progress.info("== Etapa 1: ingesta ==")
        ingest = self.ingest(progress)
        progress.info("== Etapa 2: extracción estática ==")
        extraction = self.extract(progress)
        progress.info(f"== Etapa 3: perfiles ({self.profiler_name}) ==")
        profiles = self.build_profiles(progress)
        return PipelineSummary(ingest, extraction, profiles)

    # --- CV ------------------------------------------------------------------------
    def ranking(self, role: JobRole, criteria: SelectionCriteria) -> list[RankedProject]:
        return self._cv.ranking(role, criteria)

    def generate_cv(self, role: JobRole, criteria: SelectionCriteria) -> CvResult:
        return self._cv.generate(role, criteria)

    @property
    def can_revise(self) -> bool:
        return self._reviser is not None

    def revise_cv(self, markdown: str, instruction: str) -> str:
        if self._reviser is None:
            raise RevisionRejected("Activa un modelo de Ollama en Configuración para pedir cambios al CV.")
        return self._reviser.revise(markdown, instruction)

    def save_cv(self, role: JobRole, markdown: str) -> Path:
        return self._cv.save_edit(role, markdown)

    def approve_cv(self, role: JobRole, markdown: str) -> Path:
        return self._cv.approve(role, markdown)

    # --- Consultas para la interfaz ---------------------------------------------------
    def entries(self) -> list[IndexEntry]:
        return self._index.all()

    def course_names(self) -> list[str]:
        return sorted({e.course_name for e in self._index.all()})

    def facts(self, key: str) -> Facts | None:
        return self._store.load_facts(key)

    def profile(self, key: str) -> ProjectProfile | None:
        return self._store.load_profile(key)
