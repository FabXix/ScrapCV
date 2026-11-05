"""Puestos objetivo (CAR-22). El puesto es un parámetro, no está fijo en el código."""
from __future__ import annotations

from dataclasses import dataclass

from scrapcv.domain.text import slugify, tokenize


@dataclass(frozen=True)
class JobRole:
    name: str
    keywords: frozenset[str]

    @property
    def slug(self) -> str:
        return slugify(self.name, max_len=40)

    @classmethod
    def custom(cls, name: str, keywords_text: str) -> "JobRole":
        words = [k.strip().lower() for k in keywords_text.replace(";", ",").split(",") if k.strip()]
        if len(words) <= 1:  # el usuario escribió palabras separadas por espacios
            words = sorted(tokenize(keywords_text))
        return cls(name.strip() or "Puesto personalizado", frozenset(words))


def _kw(*words: str) -> frozenset[str]:
    return frozenset(w.lower() for w in words)


DEFAULT_ROLES: tuple[JobRole, ...] = (
    JobRole("Prácticas de desarrollo backend", _kw(
        "python", "java", "c#", "go", "kotlin", "sql", "api", "rest", "flask", "django", "fastapi", "spring",
        "express", "node", "sqlalchemy", "postgresql", "mysql", "sqlite", "backend", "servidor", "base de datos",
        "concurrencia", "hilos", "junit", "junit-jupiter", "pytest", "patrón", "patron", "repository", "strategy",
        "orientada a objetos", "clases")),
    JobRole("Prácticas de desarrollo frontend", _kw(
        "javascript", "typescript", "react", "vue", "angular", "svelte", "html", "css", "vite", "axios",
        "react-router-dom", "figma", "interfaz", "spa", "frontend", "web", "prototipo", "componentes")),
    JobRole("Prácticas de ciencia de datos", _kw(
        "python", "r", "julia", "pandas", "numpy", "scikit-learn", "sklearn", "seaborn", "matplotlib", "jupyter",
        "ipynb", "datos", "modelo", "clasificación", "clasificacion", "estadística", "machine learning",
        "randomforest", "validación cruzada", "predicción", "prediccion", "sql")),
    JobRole("Prácticas de ingeniería de software y requisitos", _kw(
        "requisitos", "casos de uso", "historias de usuario", "uml", "documento de vision", "documento de visión",
        "partes interesadas", "criterios de aceptación", "criterios de aceptacion", "pruebas", "scrum",
        "docx", "pdf", "pptx", "diseño", "arquitectura")),
    JobRole("Prácticas de sistemas embebidos", _kw(
        "c", "c++", "vhdl", "verilog", "assembly", "arduino", "microcontrolador", "fpga", "sensores", "rtos")),
)


class RoleCatalog:
    def __init__(self, roles: tuple[JobRole, ...] = DEFAULT_ROLES) -> None:
        self._roles = {role.name: role for role in roles}

    def names(self) -> list[str]:
        return list(self._roles)

    def get(self, name: str) -> JobRole | None:
        return self._roles.get(name)
