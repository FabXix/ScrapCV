"""Documentos: PDF (CAR-13), Word y PowerPoint (CAR-14), notebooks (CAR-15),
texto en línea, enlaces y capturas (CAR-16)."""
from __future__ import annotations

import json
from pathlib import Path

from scrapcv.domain.facts import DocumentStat, Flag, TextSnippet
from scrapcv.domain.text import strip_html
from scrapcv.extraction.base import (
    CodeFileStat,
    ExtractionContext,
    ExtractionError,
    ExtractionResult,
    FormatExtractor,
)
from scrapcv.extraction.extractors.code import read_text
from scrapcv.extraction.links import LinkClassifier

SNIPPET_CHARS = 3000
MIN_CHARS_PER_PAGE = 25  # por debajo, el PDF probablemente es un escaneo


class _SuffixExtractor(FormatExtractor):
    suffixes: tuple[str, ...] = ()

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.suffixes


def _document_result(label: str, kind: str, text: str, units: int, links: LinkClassifier) -> ExtractionResult:
    text = text.strip()
    return ExtractionResult(
        documents=[DocumentStat(label, kind, len(text), units)],
        snippets=[TextSnippet(label, text[:SNIPPET_CHARS], 4)] if text else [],
        links=links.find(text, label),
    )


class PdfExtractor(_SuffixExtractor):
    suffixes = (".pdf",)

    def __init__(self, links: LinkClassifier) -> None:
        self._links = links

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
        except ImportError as exc:
            raise ExtractionError("falta la dependencia pypdf") from exc
        except Exception as exc:  # pypdf lanza muchos tipos distintos con PDF dañados
            raise ExtractionError(f"PDF ilegible ({exc.__class__.__name__})") from exc
        text = "\n".join(pages)
        label = ctx.label(path)
        if len(text.strip()) < MIN_CHARS_PER_PAGE * max(1, len(pages)):
            return ExtractionResult(flags=[Flag(label, "PDF escaneado o sin texto: pendiente de OCR (fase 4)")])
        return _document_result(label, "pdf", text, len(pages), self._links)


class DocxExtractor(_SuffixExtractor):
    suffixes = (".docx",)

    def __init__(self, links: LinkClassifier) -> None:
        self._links = links

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        try:
            from docx import Document

            document = Document(str(path))
        except ImportError as exc:
            raise ExtractionError("falta la dependencia python-docx") from exc
        except Exception as exc:
            raise ExtractionError(f"Word ilegible ({exc.__class__.__name__})") from exc
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return _document_result(ctx.label(path), "docx", "\n".join(parts), len(document.paragraphs), self._links)


class PptxExtractor(_SuffixExtractor):
    suffixes = (".pptx",)

    def __init__(self, links: LinkClassifier) -> None:
        self._links = links

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        try:
            from pptx import Presentation

            deck = Presentation(str(path))
        except ImportError as exc:
            raise ExtractionError("falta la dependencia python-pptx") from exc
        except Exception as exc:
            raise ExtractionError(f"PowerPoint ilegible ({exc.__class__.__name__})") from exc
        parts = []
        for number, slide in enumerate(deck.slides, start=1):
            texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame and shape.text_frame.text.strip()]
            parts.append(f"[Diapositiva {number}] " + " / ".join(texts))
        return _document_result(ctx.label(path), "pptx", "\n".join(parts), len(deck.slides), self._links)


class NotebookExtractor(_SuffixExtractor):
    suffixes = (".ipynb",)

    def __init__(self, links: LinkClassifier) -> None:
        self._links = links

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        try:
            notebook = json.loads(read_text(path))
        except ValueError as exc:
            raise ExtractionError("notebook con JSON inválido") from exc
        language = (notebook.get("metadata", {}).get("kernelspec", {}).get("language") or "python").capitalize()
        markdown, code_lines = [], 0
        cells = notebook.get("cells", [])
        for cell in cells:
            source = "".join(cell.get("source", []))
            if cell.get("cell_type") == "code":
                code_lines += sum(1 for line in source.splitlines() if line.strip())
            elif cell.get("cell_type") == "markdown":
                markdown.append(source)
        label = ctx.label(path)
        result = _document_result(label, "ipynb", "\n".join(markdown), len(cells), self._links)
        if code_lines:
            result.code.append(CodeFileStat(language, code_lines, label))
        return result


class InlineTextExtractor(FormatExtractor):
    """Texto en línea de Canvas y archivos .txt/.md/.html que no son README."""

    def __init__(self, links: LinkClassifier) -> None:
        self._links = links

    def can_handle(self, path: Path) -> bool:
        return path.name == "texto_en_linea.html" or path.suffix.lower() in (".txt", ".md", ".rst")

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        raw = read_text(path, 500_000)
        text = strip_html(raw) if path.suffix.lower() == ".html" else raw
        result = _document_result(ctx.label(path), "texto", text, 1, self._links)
        result.links = self._links.find(raw, ctx.label(path))  # los href también cuentan
        return result


class LinksManifestExtractor(FormatExtractor):
    """enlaces.json, escrito por la ingesta con los enlaces de la entrega."""

    def __init__(self, links: LinkClassifier) -> None:
        self._links = links

    def can_handle(self, path: Path) -> bool:
        return path.name == "enlaces.json"

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        try:
            urls = json.loads(read_text(path))
        except ValueError as exc:
            raise ExtractionError("enlaces.json inválido") from exc
        return ExtractionResult(links=self._links.find(" ".join(urls), "entrega (enlace)"))


class ImageExtractor(_SuffixExtractor):
    """Las capturas solo se cuentan (CAR-16); el OCR queda para la fase 4."""

    suffixes = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".heic", ".svg")

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        return ExtractionResult(images=1)
