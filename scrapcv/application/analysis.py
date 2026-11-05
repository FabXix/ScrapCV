"""Etapas 2 y 3: extracción estática (CAR-17) y perfiles (CAR-20, CAR-21).

Ambas leen la salida de la etapa anterior desde disco y funcionan sin
conexión (sección 9.4).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from scrapcv.domain.models import IndexEntry, Stage, StageStatus
from scrapcv.extraction.analyzer import StaticAnalyzer
from scrapcv.ports import AnalysisStore, IndexRepository, NullProgress, ProgressListener, ProjectProfiler, RawEvidenceStore

log = logging.getLogger("scrapcv.analysis")
_USABLE = (StageStatus.OK, StageStatus.PARTIAL)


@dataclass
class StageSummary:
    processed: int = 0
    flagged: int = 0
    errors: int = 0


class ExtractionService:
    def __init__(self, analyzer: StaticAnalyzer, raw: RawEvidenceStore, store: AnalysisStore, index: IndexRepository) -> None:
        self._analyzer = analyzer
        self._raw = raw
        self._store = store
        self._index = index

    def run(self, progress: ProgressListener = NullProgress()) -> StageSummary:
        summary = StageSummary()
        entries = [e for e in self._index.all() if e.stage(Stage.INGEST).status in _USABLE]
        for number, entry in enumerate(entries, start=1):
            progress.progress(number - 1, len(entries))
            self._extract(entry, summary, progress)
        progress.progress(len(entries), len(entries))
        self._index.save()
        return summary

    def _extract(self, entry: IndexEntry, summary: StageSummary, progress: ProgressListener) -> None:
        try:
            outcome = self._analyzer.analyze(entry.key, self._raw.folder_for(entry.key), self._store.work_folder(entry.key))
        except Exception as exc:  # una entrega con error no detiene el proceso
            summary.errors += 1
            entry.set_stage(Stage.EXTRACT, StageStatus.ERROR, [f"fallo inesperado: {exc.__class__.__name__}"])
            log.exception("Extracción falló en %s", entry.key)
            return
        self._store.save_facts(outcome.facts)
        self._store.save_snippets(entry.key, outcome.snippets)
        facts = outcome.facts
        reasons = [f"{flag.path}: {flag.reason}" for flag in facts.flags]
        if facts.credentials_skipped:
            reasons.append(f"{facts.credentials_skipped} archivo(s) de credenciales excluido(s) sin abrir")
        if not facts.has_readable_content:
            status = StageStatus.FLAGGED
            reasons = reasons or ["sin contenido legible"]
            summary.flagged += 1
            progress.warning(f"{entry.assignment_name}: marcada ({reasons[0]}).")
        else:
            status = StageStatus.PARTIAL if facts.flags else StageStatus.OK
            summary.processed += 1
            progress.info(f"{entry.assignment_name}: {facts.total_code_lines} líneas de código, "
                          f"{len(facts.documents)} documento(s).")
        entry.set_stage(Stage.EXTRACT, status, reasons)


class ProfileService:
    def __init__(self, profiler: ProjectProfiler, store: AnalysisStore, index: IndexRepository) -> None:
        self._profiler = profiler
        self._store = store
        self._index = index

    def run(self, progress: ProgressListener = NullProgress()) -> StageSummary:
        summary = StageSummary()
        entries = [e for e in self._index.all() if e.stage(Stage.EXTRACT).status in _USABLE]
        for number, entry in enumerate(entries, start=1):  # uno a la vez (sección 9.3)
            progress.progress(number - 1, len(entries))
            progress.info(f"Perfilando «{entry.assignment_name}»…")
            facts = self._store.load_facts(entry.key)
            if facts is None:
                entry.set_stage(Stage.PROFILE, StageStatus.ERROR, ["falta facts.json"])
                summary.errors += 1
                continue
            try:
                profile = self._profiler.profile(entry, facts, self._store.load_snippets(entry.key))
            except Exception as exc:
                summary.errors += 1
                entry.set_stage(Stage.PROFILE, StageStatus.ERROR, [exc.__class__.__name__])
                log.exception("Perfil falló en %s", entry.key)
                continue
            self._store.save_profile(profile)
            status = StageStatus.PARTIAL if profile.doubtful else StageStatus.OK
            entry.set_stage(Stage.PROFILE, status, profile.doubtful)
            summary.processed += 1
            self._index.save()
        progress.progress(len(entries), len(entries))
        self._index.save()
        return summary
