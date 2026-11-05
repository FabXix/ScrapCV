"""Extracción estática de hechos (CAR-17): recorre una entrega y produce Facts.

El analizador no sabe de formatos: delega en el `ExtractorRegistry`. Si un
archivo falla, lo marca y sigue (CAR-31). Nunca abre credenciales (CAR-19).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from scrapcv.domain.facts import Facts, Flag, LanguageStat, TextSnippet
from scrapcv.extraction.base import ExtractionContext, ExtractionError, ExtractionResult, ExtractorRegistry
from scrapcv.extraction.policies import CredentialPolicy, IgnoredFolderPolicy

METADATA_FILES = frozenset({"submission.json"})


@dataclass
class AnalysisOutcome:
    facts: Facts
    snippets: list[TextSnippet] = field(default_factory=list)


class FactsCollector:
    """Acumula los resultados parciales de cada extractor en un solo Facts."""

    def __init__(self, key: str) -> None:
        self.facts = Facts(key=key)
        self.snippets: list[TextSnippet] = []
        self._deps: set[str] = set()
        self._links: dict[str, object] = {}

    def add(self, result: ExtractionResult, label: str) -> None:
        facts = self.facts
        for stat in result.code:
            lang = facts.languages.setdefault(stat.language, LanguageStat())
            lang.files += 1
            lang.lines += stat.lines
            facts.code_files.append(stat.path)
        if result.dependencies:
            facts.dependency_files.append(label)
        self._deps.update(result.dependencies)
        facts.documents.extend(result.documents)
        facts.flags.extend(result.flags)
        facts.images += result.images
        facts.has_readme = facts.has_readme or result.readme
        for link in result.links:
            self._links.setdefault(link.url, link)
        self.snippets.extend(result.snippets)
        if result.code or result.documents or result.dependencies:
            facts.evidence_files.append(label)

    def flag(self, label: str, reason: str) -> None:
        self.facts.flags.append(Flag(label, reason))

    def finish(self) -> AnalysisOutcome:
        self.facts.dependencies = sorted(self._deps, key=str.lower)
        self.facts.links = list(self._links.values())  # type: ignore[arg-type]
        return AnalysisOutcome(self.facts, sorted(self.snippets, key=lambda s: s.priority))


class StaticAnalyzer:
    def __init__(
        self,
        registry: ExtractorRegistry,
        credentials: CredentialPolicy | None = None,
        ignored: IgnoredFolderPolicy | None = None,
    ) -> None:
        self._registry = registry
        self._credentials = credentials or CredentialPolicy()
        self._ignored = ignored or IgnoredFolderPolicy()

    def analyze(self, key: str, raw_dir: Path, work_dir: Path) -> AnalysisOutcome:
        collector = FactsCollector(key)
        pending = deque([ExtractionContext(base=raw_dir, label_prefix="", work_dir=work_dir, depth=0)])
        while pending:
            ctx = pending.popleft()
            for path in self._walk(ctx.base, collector):
                self._process(path, ctx, collector, pending)
        return collector.finish()

    def _walk(self, folder: Path, collector: FactsCollector):
        for path in sorted(folder.iterdir()):
            if path.is_symlink():
                continue
            if path.is_dir():
                if path.name == ".git":
                    collector.facts.has_git_history = True  # extensión futura (CAR-12)
                if not self._ignored.is_ignored(path):
                    yield from self._walk(path, collector)
            elif path.is_file() and path.name not in METADATA_FILES and not path.name.endswith(".part"):
                yield path

    def _process(self, path: Path, ctx: ExtractionContext, collector: FactsCollector, pending: deque) -> None:
        label = ctx.label(path)
        collector.facts.files_seen += 1
        if self._credentials.is_sensitive(path):
            collector.facts.credentials_skipped += 1  # se cuenta, nunca se abre
            return
        extractor = self._registry.find(path)
        if extractor is None:
            collector.flag(label, "formato no soportado")
            return
        try:
            result = extractor.extract(path, ctx)
        except ExtractionError as exc:
            collector.flag(label, str(exc))
            return
        except OSError as exc:
            collector.flag(label, f"no se pudo leer ({exc.__class__.__name__})")
            return
        collector.add(result, label)
        for archive in result.unpacked:
            pending.append(ExtractionContext(archive.folder, archive.label, ctx.work_dir, ctx.depth + 1))
