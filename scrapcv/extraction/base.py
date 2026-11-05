"""Contrato de los extractores de formato.

Agregar un formato nuevo = escribir una clase que cumpla `FormatExtractor` y
registrarla (sección 7.1 Mantenibilidad). El analizador no cambia.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from scrapcv.domain.facts import DocumentStat, Flag, LinkRef, TextSnippet


class ExtractionError(Exception):
    """El archivo no pudo leerse; se registra y se sigue con el siguiente (CAR-31)."""


@dataclass(frozen=True)
class CodeFileStat:
    language: str
    lines: int
    path: str


@dataclass(frozen=True)
class UnpackedArchive:
    folder: Path
    label: str  # cómo se muestra en la rastreabilidad: "entrega.zip!/"


@dataclass
class ExtractionResult:
    code: list[CodeFileStat] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    documents: list[DocumentStat] = field(default_factory=list)
    snippets: list[TextSnippet] = field(default_factory=list)
    links: list[LinkRef] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    images: int = 0
    readme: bool = False
    unpacked: list[UnpackedArchive] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractionContext:
    base: Path  # carpeta contra la que se calculan rutas relativas
    label_prefix: str  # prefijo visible (p. ej. "entrega.zip!/")
    work_dir: Path  # dónde se pueden descomprimir archivos
    depth: int = 0

    def label(self, path: Path) -> str:
        return self.label_prefix + path.relative_to(self.base).as_posix()


class FormatExtractor(ABC):
    @abstractmethod
    def can_handle(self, path: Path) -> bool: ...

    @abstractmethod
    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult: ...


class ExtractorRegistry:
    """Encuentra el extractor de un archivo. El orden de registro es la prioridad."""

    def __init__(self, extractors: list[FormatExtractor] | None = None) -> None:
        self._extractors: list[FormatExtractor] = list(extractors or [])

    def register(self, extractor: FormatExtractor) -> "ExtractorRegistry":
        self._extractors.append(extractor)
        return self

    def find(self, path: Path) -> FormatExtractor | None:
        return next((e for e in self._extractors if e.can_handle(path)), None)
