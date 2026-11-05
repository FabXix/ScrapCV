"""Estrategias para generar el perfil de un proyecto (CAR-20).

- `LlmProjectProfiler`: usa el modelo local con contexto acotado y guardas.
- `StaticProjectProfiler`: sin modelo, solo con hechos (útil sin Ollama).
- `FallbackProjectProfiler`: intenta la primera y, si falla, usa la segunda.
Las tres cumplen el mismo contrato `ProjectProfiler` (LSP).
"""
from __future__ import annotations

import logging
from typing import Iterable

from scrapcv.analysis.context import ContextBuilder
from scrapcv.analysis.guards import GroupWorkGuard, NumberGuard, ProfileValidator, TechnologyEvidenceGuard
from scrapcv.domain.facts import Facts, ProjectProfile, TextSnippet
from scrapcv.domain.models import IndexEntry
from scrapcv.ports import LanguageModel, ProjectProfiler

log = logging.getLogger("scrapcv.profiler")

SYSTEM_PROMPT = """Eres un asistente que resume entregas académicas para un currículum.
Reglas estrictas:
- Usa SOLO la evidencia proporcionada (hechos y fragmentos de archivos). No inventes.
- NO escribas números, cifras, porcentajes ni métricas de ningún tipo.
- Describe lo que el estudiante ENTREGÓ, no lo que pedía la tarea.
- Si algo es incierto, ponlo en "dudoso".
- Escribe en español, frases breves, con verbos en pasado (ej. "Desarrolló", "Diseñó").
Responde únicamente un objeto JSON con estas claves:
{"resumen": str, "tecnologias": [str], "habilidades": [str], "alcance": str, "rol": str, "dudoso": [str]}"""


def _as_list(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


class LlmProjectProfiler(ProjectProfiler):
    def __init__(self, model: LanguageModel, context: ContextBuilder | None = None) -> None:
        self._model = model
        self._context = context or ContextBuilder()

    def profile(self, entry: IndexEntry, facts: Facts, snippets: Iterable[TextSnippet]) -> ProjectProfile:
        snippets = list(snippets)
        bounded = self._context.build(entry, facts, snippets)
        prompt = f"Evidencia de la entrega:\n{bounded.text}\n\nGenera el JSON del perfil."
        data = self._model.complete_json(SYSTEM_PROMPT, prompt)
        profile = ProjectProfile(
            key=entry.key,
            summary=str(data.get("resumen", "")).strip(),
            technologies=_as_list(data.get("tecnologias")),
            skills=_as_list(data.get("habilidades")),
            scope=str(data.get("alcance", "")).strip(),
            role=str(data.get("rol", "")).strip(),
            doubtful=_as_list(data.get("dudoso")),
            origin=self._model.name,
            sources=bounded.sources,
        )
        validator = ProfileValidator([NumberGuard(), TechnologyEvidenceGuard(), GroupWorkGuard(entry.is_group)])
        return validator.validate(profile, ContextBuilder.evidence_corpus(facts, snippets))


class StaticProjectProfiler(ProjectProfiler):
    def profile(self, entry: IndexEntry, facts: Facts, snippets: Iterable[TextSnippet]) -> ProjectProfile:
        languages = sorted(facts.languages, key=lambda l: -facts.languages[l].lines)
        kinds = sorted({d.kind for d in facts.documents if d.kind != "readme"})
        pieces = []
        if languages:
            pieces.append("código en " + ", ".join(languages))
        if kinds:
            pieces.append("documentación (" + ", ".join(kinds) + ")")
        what = " y ".join(pieces) or "evidencia registrada"
        profile = ProjectProfile(
            key=entry.key,
            summary=f"Entregó «{entry.assignment_name}» con {what}.",
            technologies=languages + facts.dependencies[:6],
            scope=entry.course_name,
            role="",
            doubtful=["Resumen generado sin modelo de lenguaje: redacta con tus palabras lo que construiste."],
            origin="estatico",
            sources=[s.source for s in list(snippets)[:5]],
        )
        return ProfileValidator([GroupWorkGuard(entry.is_group)]).validate(profile, "")


class FallbackProjectProfiler(ProjectProfiler):
    def __init__(self, primary: ProjectProfiler, fallback: ProjectProfiler) -> None:
        self._primary = primary
        self._fallback = fallback

    def profile(self, entry: IndexEntry, facts: Facts, snippets: Iterable[TextSnippet]) -> ProjectProfile:
        snippets = list(snippets)
        try:
            return self._primary.profile(entry, facts, snippets)
        except Exception as exc:  # el modelo puede fallar de muchas formas; nunca detiene el proceso
            log.warning("Perfil con modelo falló para %s: %s", entry.key, exc.__class__.__name__)
            profile = self._fallback.profile(entry, facts, snippets)
            profile.doubtful.insert(0, "El modelo local no respondió; se usó el perfil estático.")
            return profile
