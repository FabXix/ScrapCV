"""Vacante a la que el estudiante quiere aplicar (entrada principal del CV a la medida)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobPosting:
    """Lo que pide la vacante, ya separado en requisitos.

    Los requisitos se guardan con su nombre legible («Node.js», «Trabajo en equipo»);
    la comparación con la evidencia se hace con el catálogo de `domain.skills`.
    """

    title: str
    raw_text: str = ""
    company: str = ""
    required: tuple[str, ...] = ()  # técnicos indispensables
    preferred: tuple[str, ...] = ()  # técnicos deseables
    soft_skills: tuple[str, ...] = ()
    other: tuple[str, ...] = ()  # lo que la evidencia no puede comprobar (inglés, titulación, horario…)
    responsibilities: tuple[str, ...] = ()
    source: str = "palabras clave"  # «palabras clave» o el nombre del modelo

    @property
    def technical(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.required + self.preferred))

    @property
    def is_empty(self) -> bool:
        return not (self.required or self.preferred or self.soft_skills)
