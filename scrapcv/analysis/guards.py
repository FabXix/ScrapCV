"""Guardas de veracidad sobre la salida del modelo (CAR-21, sección 6.1 Cifras).

Cada guarda hace una sola cosa y se pueden combinar (Chain of Responsibility
simple): el validador las aplica en orden sobre un perfil.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from scrapcv.domain.facts import ProjectProfile

_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?\s*(?:%|por ciento|k\b|mil\b)?")


def strip_numbers(text: str) -> str:
    """Quita cifras de un texto escrito por el modelo (las cifras salen solo de `Facts`)."""
    return re.sub(r"\s{2,}", " ", _NUMBER.sub("", text)).strip(" ,;")


class ProfileGuard(ABC):
    @abstractmethod
    def apply(self, profile: ProjectProfile, evidence: str) -> None: ...


class NumberGuard(ProfileGuard):
    """El modelo no genera cifras: se eliminan y se avisa al usuario."""

    def apply(self, profile: ProjectProfile, evidence: str) -> None:
        removed = False
        for attr in ("summary", "scope", "role"):
            original = getattr(profile, attr)
            cleaned = self._strip(original)
            if cleaned != original:
                removed = True
                setattr(profile, attr, cleaned)
        cleaned_skills = [self._strip(s) for s in profile.skills]
        removed = removed or cleaned_skills != profile.skills
        profile.skills = [s for s in cleaned_skills if s]
        if removed:
            profile.doubtful.append("El modelo propuso cifras; se eliminaron. Las cifras del CV salen solo del análisis estático.")

    @staticmethod
    def _strip(text: str) -> str:
        return re.sub(r"\s{2,}", " ", _NUMBER.sub("", text)).strip(" ,;")


class TechnologyEvidenceGuard(ProfileGuard):
    """Solo se aceptan tecnologías que aparecen en la evidencia."""

    def apply(self, profile: ProjectProfile, evidence: str) -> None:
        accepted = []
        for tech in profile.technologies:
            if self._mentioned(tech, evidence):
                accepted.append(tech)
            else:
                profile.doubtful.append(f"Tecnología sin respaldo en los archivos: {tech}")
        profile.technologies = accepted

    @staticmethod
    def _mentioned(tech: str, evidence: str) -> bool:
        needle = tech.lower().strip()
        if not needle:
            return False
        if needle in evidence:
            return True
        compact = re.sub(r"[\s\-_.]", "", needle)  # "React Router DOM" ≈ "react-router-dom"
        if compact and compact in re.sub(r"[\s\-_.]", "", evidence):
            return True
        aliases = {"scikit-learn": "sklearn", "sklearn": "scikit-learn", "react.js": "react", "node.js": "node"}
        return aliases.get(needle, "\0") in evidence


class GroupWorkGuard(ProfileGuard):
    """En trabajos de equipo no se atribuye todo al usuario (N5)."""

    def __init__(self, is_group: bool) -> None:
        self._is_group = is_group

    def apply(self, profile: ProjectProfile, evidence: str) -> None:
        if not self._is_group:
            return
        profile.role = "Proyecto en equipo. " + (profile.role or "")
        profile.doubtful.append("Proyecto grupal: confirma qué partes hiciste tú (el cálculo por commits es una extensión futura).")


class ProfileValidator:
    def __init__(self, guards: list[ProfileGuard]) -> None:
        self._guards = guards

    def validate(self, profile: ProjectProfile, evidence: str) -> ProjectProfile:
        for guard in self._guards:
            guard.apply(profile, evidence)
        profile.doubtful = list(dict.fromkeys(profile.doubtful))  # sin duplicados, mismo orden
        return profile
