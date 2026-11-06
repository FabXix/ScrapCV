"""Raíz de composición: el único lugar que conoce las clases concretas.

Aquí se decide qué implementación va detrás de cada puerto (Canvas real o
demo, Ollama o perfil estático, Markdown como formato de salida). Cambiar una
pieza no obliga a tocar las demás.
"""
from __future__ import annotations

from pathlib import Path

from scrapcv.analysis.profilers import FallbackProjectProfiler, LlmProjectProfiler, StaticProjectProfiler
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
from scrapcv.ports import ProjectProfiler
from scrapcv.ranking.ranker import WeightedRanker
from scrapcv.ranking.roles import RoleCatalog
from scrapcv.domain.models import ContactInfo
from scrapcv.writing.cv import CvComposer, MarkdownCvRenderer
from scrapcv.writing.resume import ResumeBuilder, ResumeWriter


class MissingTokenError(ValueError):
    pass


def _gateway(settings: Settings, token: str | None):
    if settings.use_demo:
        return DemoCanvasGateway()
    if not token:
        raise MissingTokenError("Escribe tu token de Canvas o define la variable CANVAS_TOKEN.")
    REDACTOR.register(token)
    return CanvasApiGateway(CanvasHttpClient(settings.canvas_url, token))


def _profiler(settings: Settings) -> tuple[ProjectProfiler, str]:
    static = StaticProjectProfiler()
    if not settings.use_llm or not settings.ollama_model:
        return static, "perfil estático"
    model = OllamaLanguageModel(settings.ollama_url, settings.ollama_model)
    return FallbackProjectProfiler(LlmProjectProfiler(model), static), model.name


def _reviser(settings: Settings) -> CvReviser | None:
    if not settings.use_llm or not settings.ollama_model:
        return None
    return CvReviser(OllamaLanguageModel(settings.ollama_url, settings.ollama_model))


def _resume_model(settings: Settings) -> OllamaLanguageModel | None:
    if not settings.use_llm or not settings.ollama_model:
        return None
    return OllamaLanguageModel(settings.ollama_url, settings.ollama_model)


def build_app(settings: Settings, token: str | None) -> ScrapCvFacade:
    layout = DataLayout(Path(settings.data_dir))
    configure_logging(layout.logs)
    gateway = _gateway(settings, token)

    index = JsonIndexRepository(layout)
    raw = FileRawEvidenceStore(layout)
    store = FileAnalysisStore(layout)
    users = JsonUserRepository(layout)
    profiler, profiler_name = _profiler(settings)

    return ScrapCvFacade(
        reader=gateway,
        ingest=IngestService(gateway, gateway, raw, index, users),
        extraction=ExtractionService(StaticAnalyzer(default_registry()), raw, store, index),
        profiles=ProfileService(profiler, store, index),
        cv=CvService(
            index, store, users, WeightedRanker(), CvComposer(), MarkdownCvRenderer(), FileCvRepository(layout),
            resume=ResumeBuilder(ResumeWriter(_resume_model(settings))),
            contact=ContactInfo(settings.phone, settings.location, settings.linkedin, settings.github, settings.portfolio),
        ),
        index=index,
        store=store,
        roles=RoleCatalog(),
        data_dir=layout.root,
        profiler_name=profiler_name,
        reviser=_reviser(settings),
    )


def list_ollama_models(settings: Settings) -> list[str]:
    try:
        return OllamaLanguageModel(settings.ollama_url, "-").list_models()
    except ValueError:
        return []
