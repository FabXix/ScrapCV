"""Hechos estáticos de una entrega (facts.json) y perfil de proyecto (perfil.json).

Regla de veracidad (sección 6.1): todo número que aparezca en el CV sale de
`Facts`, nunca del modelo de lenguaje.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class LanguageStat:
    files: int = 0
    lines: int = 0


@dataclass(frozen=True)
class DocumentStat:
    path: str
    kind: str  # pdf | docx | pptx | ipynb | texto
    chars: int
    units: int = 0  # páginas, diapositivas o celdas


@dataclass(frozen=True)
class LinkRef:
    url: str
    kind: str  # repositorio | drive | figma | youtube | otro
    source: str = ""


@dataclass(frozen=True)
class Flag:
    path: str
    reason: str


@dataclass(frozen=True)
class TextSnippet:
    """Fragmento de texto para el contexto acotado del modelo (no va al CV)."""

    source: str
    text: str
    priority: int = 5  # 1 = más importante


@dataclass
class Facts:
    key: str
    languages: dict[str, LanguageStat] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    documents: list[DocumentStat] = field(default_factory=list)
    links: list[LinkRef] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    images: int = 0
    files_seen: int = 0
    credentials_skipped: int = 0
    has_readme: bool = False
    has_git_history: bool = False  # extensión futura: solo se detecta
    evidence_files: list[str] = field(default_factory=list)
    code_files: list[str] = field(default_factory=list)
    dependency_files: list[str] = field(default_factory=list)

    @property
    def total_code_lines(self) -> int:
        return sum(stat.lines for stat in self.languages.values())

    @property
    def total_code_files(self) -> int:
        return sum(stat.files for stat in self.languages.values())

    @property
    def document_chars(self) -> int:
        return sum(doc.chars for doc in self.documents)

    @property
    def has_readable_content(self) -> bool:
        return bool(self.total_code_lines or self.document_chars > 40)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["total_code_lines"] = self.total_code_lines
        data["total_code_files"] = self.total_code_files
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Facts":
        return cls(
            key=data["key"],
            languages={k: LanguageStat(**v) for k, v in data.get("languages", {}).items()},
            dependencies=list(data.get("dependencies", [])),
            documents=[DocumentStat(**d) for d in data.get("documents", [])],
            links=[LinkRef(**l) for l in data.get("links", [])],
            flags=[Flag(**f) for f in data.get("flags", [])],
            images=data.get("images", 0),
            files_seen=data.get("files_seen", 0),
            credentials_skipped=data.get("credentials_skipped", 0),
            has_readme=data.get("has_readme", False),
            has_git_history=data.get("has_git_history", False),
            evidence_files=list(data.get("evidence_files", [])),
            code_files=list(data.get("code_files", [])),
            dependency_files=list(data.get("dependency_files", [])),
        )


@dataclass
class ProjectProfile:
    """perfil.json: qué hace el proyecto, según el modelo local o el análisis estático."""

    key: str
    summary: str
    technologies: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    scope: str = ""
    role: str = ""
    doubtful: list[str] = field(default_factory=list)  # CAR-21: lo que el usuario debe verificar
    origin: str = "estatico"
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectProfile":
        return cls(**data)
