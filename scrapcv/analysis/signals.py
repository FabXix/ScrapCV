"""Señales verificables de habilidades blandas: sin señal en la evidencia, no hay habilidad."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapcv.ranking.ranker import RankedProject


@dataclass
class SoftSignal:
    name: str  # cómo se ve en el CV
    description: str  # lo que ve el modelo
    projects: list[str] = field(default_factory=list)  # claves de las entregas que la respaldan


def soft_signals(ranked: list["RankedProject"]) -> dict[str, SoftSignal]:
    signals: dict[str, SoftSignal] = {}

    def add(sid: str, name: str, description: str, key: str) -> None:
        signals.setdefault(sid, SoftSignal(name, description)).projects.append(key)

    for r in ranked:
        entry, facts = r.candidate.entry, r.candidate.facts
        if entry.is_group:
            add("trabajo_en_equipo", "Trabajo en equipo", "Entregó proyectos grupales en la carrera.", entry.key)
        if any(d.kind == "pptx" for d in facts.documents) or any(link.kind == "youtube" for link in facts.links):
            add("comunicacion", "Comunicación", "Entregó presentaciones o videos para exponer sus proyectos.", entry.key)
        if facts.has_readme or any(d.kind in ("pdf", "docx") for d in facts.documents):
            name = "Documentación técnica" if facts.languages else "Redacción de reportes"
            add("documentacion", name, "Entregó reportes o README que explican sus proyectos.", entry.key)
    languages = {lang for r in ranked for lang in r.candidate.facts.languages}
    if len(languages) >= 3:
        signals["aprendizaje"] = SoftSignal(
            "Aprendizaje continuo", "Usó varios lenguajes de programación en sus proyectos.",
            [r.candidate.entry.key for r in ranked],
        )
    return signals
