"""Raíz de composición: el único lugar que conoce las clases concretas.

Aquí se decide qué implementación va detrás de cada puerto (Canvas real o
demo, Ollama o perfil estático, Markdown como formato de salida). Cambiar una
pieza no obliga a tocar las demás.
"""
from __future__ import annotations

from pathlib import Path

from scrapcv.analysis.posting import FallbackPostingAnalyzer, KeywordPostingAnalyzer, LlmPostingAnalyzer
from scrapcv.analysis.profilers import FallbackProjectProfiler, LlmProjectProfiler, StaticProjectProfiler
from scrapcv.application.advice import CvAdvisor
from scrapcv.application.analysis import ExtractionService, ProfileService
from scrapcv.application.cv_revision import CvReviser
from scrapcv.application.cv_service import CvService
from scrapcv.application.facade import ScrapCvFacade
from scrapcv.application.ingest import IngestService
from scrapcv.extraction.analyzer import StaticAnalyzer
from scrapcv.extraction.factory import default_registry
from scrapcv.infrastructure.canvas.api_gateway import CanvasApiGateway
from scrapcv.infrastructure.canvas.demo_gateway import DemoCanvasGateway
from scrapcv.infrastructure.canvas.http_client import CanvasHttpClient
from scrapcv.infrastructure.config import Settings
from scrapcv.infrastructure.logging_setup import REDACTOR, configure_logging
from scrapcv.infrastructure.ollama import OllamaLanguageModel
from scrapcv.infrastructure.storage import (
    DataLayout,
    FileAnalysisStore,
    FileCvRepository,
    FileRawEvidenceStore,
    JsonIndexRepository,
    JsonUserRepository,
)
from scrapcv.ports import LanguageModel, PostingAnalyzer, ProjectProfiler
from scrapcv.ranking.match import MatchAnalyzer
from scrapcv.ranking.ranker import WeightedRanker
from scrapcv.ranking.roles import RoleCatalog
from scrapcv.writing.cv import CvComposer, MarkdownCvRenderer
from scrapcv.writing.export import DEFAULT_EXPORTERS
from scrapcv.writing.resume import ResumeBuilder
from scrapcv.writing.writers import LlmResumeWriter, ResumeWriter, RuleBasedResumeWriter, WriterChain


class MissingTokenError(ValueError):
    pass


def _gateway(settings: Settings, token: str | None):
    if settings.use_demo:
        return DemoCanvasGateway()
    if not token:
        raise MissingTokenError("Escribe tu token de Canvas o define la variable CANVAS_TOKEN.")
    REDACTOR.register(token)
    return CanvasApiGateway(CanvasHttpClient(settings.canvas_url, token))


def _language_model(settings: Settings) -> LanguageModel | None:
    """Único lugar que decide si hay modelo. Cambiar de proveedor de IA = cambiar esta función."""
    if not settings.use_llm or not settings.ollama_model:
        return None
    return OllamaLanguageModel(settings.ollama_url, settings.ollama_model)


def _profiler(model: LanguageModel | None) -> ProjectProfiler:
    static = StaticProjectProfiler()
    return FallbackProjectProfiler(LlmProjectProfiler(model), static) if model else static


def _posting_analyzer(model: LanguageModel | None) -> PostingAnalyzer:
    keywords = KeywordPostingAnalyzer()
    return FallbackPostingAnalyzer(LlmPostingAnalyzer(model, keywords), keywords) if model else keywords


def _writers(model: LanguageModel | None) -> WriterChain:
    writers: list[ResumeWriter] = [LlmResumeWriter(model)] if model else []
    return WriterChain(writers + [RuleBasedResumeWriter()])


def build_app(settings: Settings, token: str | None) -> ScrapCvFacade:
    # Los datos de ejemplo viven aparte para no mezclarse nunca con las entregas reales.
    layout = DataLayout(Path(settings.data_dir) / "ejemplo" if settings.use_demo else Path(settings.data_dir))
    configure_logging(layout.logs)
    gateway = _gateway(settings, token)
    model = _language_model(settings)  # una sola instancia para perfiles, vacante, CV y revisión

    index = JsonIndexRepository(layout)
    raw = FileRawEvidenceStore(layout)
    store = FileAnalysisStore(layout)
    users = JsonUserRepository(layout)
    writers = _writers(model)

    return ScrapCvFacade(
        reader=gateway,
        ingest=IngestService(gateway, gateway, raw, index, users),
        extraction=ExtractionService(StaticAnalyzer(default_registry()), raw, store, index),
        profiles=ProfileService(_profiler(model), store, index),
        cv=CvService(
            index, store, users, WeightedRanker(), CvComposer(), MarkdownCvRenderer(), FileCvRepository(layout),
            resume=ResumeBuilder(writers),
            advisor=CvAdvisor(MatchAnalyzer(), writers),
            contact=settings.contact(),
            exporters=DEFAULT_EXPORTERS,
        ),
        index=index,
        store=store,
        roles=RoleCatalog(),
        data_dir=layout.root,
        profiler_name=model.name if model else "perfil estático",
        posting_analyzer=_posting_analyzer(model),
        reviser=CvReviser(model) if model else None,
    )


def list_ollama_models(settings: Settings) -> list[str]:
    try:
        return OllamaLanguageModel(settings.ollama_url, "-").list_models()
    except ValueError:
        return []
