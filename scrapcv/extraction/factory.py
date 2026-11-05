"""Arma el registro de extractores por defecto.

Para soportar un formato nuevo basta con añadir una línea aquí (o llamar a
`registry.register(...)` desde fuera); el analizador no se modifica.
"""
from __future__ import annotations

from scrapcv.extraction.base import ExtractorRegistry
from scrapcv.extraction.extractors.archives import SevenZipExtractor, TarExtractor, ZipExtractor
from scrapcv.extraction.extractors.code import DependencyManifestExtractor, ReadmeExtractor, SourceCodeExtractor
from scrapcv.extraction.extractors.documents import (
    DocxExtractor,
    ImageExtractor,
    InlineTextExtractor,
    LinksManifestExtractor,
    NotebookExtractor,
    PdfExtractor,
    PptxExtractor,
)
from scrapcv.extraction.links import LinkClassifier


def default_registry() -> ExtractorRegistry:
    links = LinkClassifier()
    return ExtractorRegistry([
        # Los más específicos primero.
        LinksManifestExtractor(links),
        ReadmeExtractor(),
        DependencyManifestExtractor(),
        InlineTextExtractor(links),
        ZipExtractor(),
        TarExtractor(),
        SevenZipExtractor(),
        NotebookExtractor(links),
        PdfExtractor(links),
        DocxExtractor(links),
        PptxExtractor(links),
        ImageExtractor(),
        SourceCodeExtractor(),
    ])
