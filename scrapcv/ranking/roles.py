"""Puestos objetivo (CAR-22). El puesto es un parámetro, no está fijo en el código."""
from __future__ import annotations

from dataclasses import dataclass

from scrapcv.domain.posting import JobPosting
from scrapcv.domain.skills import canonical, normalize
from scrapcv.domain.text import slugify, tokenize


PHRASE = "~"  # marca de un requisito en lenguaje natural: se compara por palabras, no exacto


@dataclass(frozen=True)
class JobRole:
    name: str
    keywords: frozenset[str]
    # Cada requisito con sus formas equivalentes ({"node.js", "node", "nodejs"}).
    # Vacío = cada palabra clave es un requisito por separado.
    requirements: tuple[frozenset[str], ...] = ()
    posting: JobPosting | None = None

    @property
    def slug(self) -> str:
        return slugify(self.name, max_len=40)

    def requirement_groups(self) -> tuple[frozenset[str], ...]:
        return self.requirements or tuple(frozenset({k}) for k in sorted(self.keywords))

    @classmethod
    def from_posting(cls, posting: JobPosting) -> "JobRole":
        groups = []
        for requirement in posting.technical:
            skill = canonical(requirement)
            groups.append(frozenset(skill.forms) if skill else frozenset({PHRASE + normalize(requirement)}))
        if not groups and posting.title:
            groups.append(frozenset({PHRASE + normalize(posting.title)}))  # vacante sin requisitos: al menos el puesto
        keywords = frozenset(form for group in groups for form in group)
        return cls(posting.title or "Vacante", keywords, tuple(groups), posting)

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
