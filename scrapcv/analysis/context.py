"""Contexto acotado para el modelo (sección 8.2): hechos + README + archivos clave.

Nunca se manda el proyecto completo: se respeta un presupuesto de caracteres
y se priorizan los fragmentos más informativos.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from scrapcv.domain.facts import Facts, TextSnippet
from scrapcv.domain.models import IndexEntry


@dataclass(frozen=True)
class BoundedContext:
    text: str
    sources: list[str]


class ContextBuilder:
    def __init__(self, budget_chars: int = 7000, max_per_snippet: int = 2000) -> None:
        self._budget = budget_chars
        self._per_snippet = max_per_snippet

    def build(self, entry: IndexEntry, facts: Facts, snippets: Iterable[TextSnippet]) -> BoundedContext:
        header = self.facts_summary(entry, facts)
        parts, sources, used = [header], [], len(header)
        for snippet in sorted(snippets, key=lambda s: s.priority):
            chunk = snippet.text.strip()[: self._per_snippet]
            if not chunk:
                continue
            block = f"\n--- Archivo: {snippet.source} ---\n{chunk}\n"
            if used + len(block) > self._budget:
                continue
            parts.append(block)
            sources.append(snippet.source)
            used += len(block)
        return BoundedContext("".join(parts), sources)

    @staticmethod
    def facts_summary(entry: IndexEntry, facts: Facts) -> str:
        languages = ", ".join(sorted(facts.languages)) or "ninguno"
        documents = ", ".join(sorted({d.kind for d in facts.documents})) or "ninguno"
        deps = ", ".join(facts.dependencies[:25]) or "ninguna"
        group = "sí" if entry.is_group else "no"
        return (
            f"Materia: {entry.course_name}\nTarea: {entry.assignment_name}\nTrabajo grupal: {group}\n"
            f"Lenguajes detectados: {languages}\nDependencias: {deps}\nTipos de documento: {documents}\n"
        )

    @staticmethod
    def evidence_corpus(facts: Facts, snippets: Iterable[TextSnippet]) -> str:
        """Todo el texto contra el que se verifica lo que dice el modelo."""
        parts = list(facts.languages) + facts.dependencies + [s.text for s in snippets]
        return "\n".join(parts).lower()
