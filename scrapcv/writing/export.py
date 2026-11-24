"""Exportación del CV a formatos para enviar (HTML imprimible a PDF y Word).

El usuario edita el CV en Markdown, así que los exportadores leen Markdown: un
subconjunto pequeño (títulos, párrafos, viñetas, **negritas**, *cursivas* y
[enlaces](url)), que es todo lo que genera `ResumeBuilder`. Los comentarios HTML
y las marcas de evidencia del borrador original se descartan.
"""
from __future__ import annotations

import html
import io
import re
from dataclasses import dataclass, field

from scrapcv.ports import CvExporter

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_SUB = re.compile(r"<sub>.*?</sub>", re.S)
_INLINE = re.compile(r"(\*\*[^*]+\*\*|\[[^\]]+\]\([^)\s]+\)|\*[^*\s][^*]*\*|_[^_\s][^_]*_)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


@dataclass
class Block:
    kind: str  # h1 | h2 | h3 | p | ul
    text: str = ""
    items: list[str] = field(default_factory=list)

    @property
    def is_meta(self) -> bool:
        """Línea completa en cursiva bajo un proyecto («*Proyecto en equipo · Materia · Dic 2025*»)."""
        return self.kind == "p" and bool(re.fullmatch(r"\*[^*].*\*|_[^_].*_", self.text))


def parse(markdown: str) -> list[Block]:
    text = _SUB.sub("", _COMMENT.sub("", markdown))
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(Block("p", " ".join(paragraph)))
            paragraph.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        heading = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        bullet = re.match(r"^[-*+]\s+(.*)$", stripped)
        if not stripped:
            flush()
        elif heading:
            flush()
            blocks.append(Block(f"h{len(heading.group(1))}", heading.group(2).strip()))
        elif bullet:
            flush()
            if blocks and blocks[-1].kind == "ul":
                blocks[-1].items.append(bullet.group(1).strip())
            else:
                blocks.append(Block("ul", items=[bullet.group(1).strip()]))
        else:
            if blocks and blocks[-1].kind == "ul" and raw.startswith((" ", "\t")) and not paragraph:
                blocks[-1].items[-1] += " " + stripped  # continuación de una viñeta
            else:
                paragraph.append(stripped)
    flush()
    return blocks


def tokens(text: str) -> list[tuple[str, str, str]]:
    """Divide una línea en (tipo, texto, url): tipo = plain | bold | italic | link."""
    out = []
    for piece in _INLINE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**"):
            out.append(("bold", piece[2:-2], ""))
        elif (link := _LINK.fullmatch(piece)):
            out.append(("link", link.group(1), link.group(2)))
        elif len(piece) > 2 and piece[0] == piece[-1] and piece[0] in "*_":
            out.append(("italic", piece[1:-1], ""))
        else:
            out.append(("plain", piece, ""))
    return out


# --- HTML (se abre en el navegador; «Guardar como PDF» desde ahí) ------------------------------------

_CSS = """
@page { size: A4; margin: 15mm 17mm; }
* { box-sizing: border-box; }
body { font-family: "Calibri", "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: #1f2937; font-size: 10.5pt;
       line-height: 1.45; background: #eef1f6; margin: 0; }
.page { background: #fff; max-width: 210mm; margin: 24px auto; padding: 18mm 19mm; box-shadow: 0 4px 24px rgba(15,23,42,.12); }
header { margin-bottom: 6px; }
h1 { font-size: 25pt; margin: 0; letter-spacing: .3px; color: #0f172a; font-weight: 700; }
.headline { color: #2f5bea; font-size: 12.5pt; font-weight: 600; margin: 2px 0 6px; }
.contact { color: #475569; font-size: 9.5pt; margin: 0; }
h2 { font-size: 10.5pt; text-transform: uppercase; letter-spacing: 1.6px; color: #1e3a8a; margin: 18px 0 8px;
     padding-bottom: 4px; border-bottom: 1.5px solid #c7d2fe; }
h3 { font-size: 11pt; margin: 12px 0 0; color: #0f172a; }
h3 a { font-weight: 400; font-size: 9.5pt; }
p { margin: 0 0 6px; }
p.meta { color: #64748b; font-size: 9.5pt; margin: 1px 0 4px; }
ul { margin: 3px 0 6px; padding-left: 18px; }
li { margin: 2px 0; }
li::marker { color: #94a3b8; }
a { color: #2f5bea; text-decoration: none; }
strong { color: #0f172a; }
.toolbar { max-width: 210mm; margin: 16px auto 0; text-align: right; font-family: "Segoe UI", Arial, sans-serif; }
.toolbar button { background: #2f5bea; color: #fff; border: 0; border-radius: 6px; padding: 8px 16px; font-size: 10pt; cursor: pointer; }
@media print { body { background: #fff; } .page { box-shadow: none; margin: 0; padding: 0; max-width: none; } .toolbar { display: none; } }
"""


def _inline_html(text: str) -> str:
    parts = []
    for kind, value, url in tokens(text):
        value = html.escape(value)
        if kind == "bold":
            parts.append(f"<strong>{value}</strong>")
        elif kind == "italic":
            parts.append(f"<em>{value}</em>")
        elif kind == "link":
            safe = url if url.startswith(("http://", "https://", "mailto:")) else "#"
            parts.append(f'<a href="{html.escape(safe, quote=True)}">{value}</a>')
        else:
            parts.append(value)
    return "".join(parts)


class HtmlCvExporter(CvExporter):
    key = "html"
    label = "Vista previa / PDF"
    extension = "html"

    def export(self, markdown: str) -> bytes:
        blocks = parse(markdown)
        title = next((b.text for b in blocks if b.kind == "h1"), "Currículum")
        body: list[str] = []
        in_header = False
        for i, block in enumerate(blocks):
            if block.kind == "h1":
                body.append(f"<header><h1>{_inline_html(block.text)}</h1>")
                in_header = True
                continue
            if in_header and block.kind != "p":
                body.append("</header>")
                in_header = False
            if in_header:
                headline = re.fullmatch(r"\*\*(.+)\*\*", block.text)
                body.append(f'<p class="headline">{html.escape(headline.group(1))}</p>' if headline
                            else f'<p class="contact">{_inline_html(block.text)}</p>')
            elif block.kind in ("h2", "h3"):
                body.append(f"<{block.kind}>{_inline_html(block.text)}</{block.kind}>")
            elif block.kind == "ul":
                body.append("<ul>" + "".join(f"<li>{_inline_html(item)}</li>" for item in block.items) + "</ul>")
            else:
                css = ' class="meta"' if block.is_meta else ""
                text = block.text[1:-1] if block.is_meta else block.text
                body.append(f"<p{css}>{_inline_html(text)}</p>")
        if in_header:
            body.append("</header>")
        page = (
            "<!DOCTYPE html>\n<html lang=\"es\"><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)} · CV</title><style>{_CSS}</style></head><body>"
            '<div class="toolbar"><button onclick="window.print()">Guardar como PDF</button></div>'
            f'<main class="page">{"".join(body)}</main></body></html>\n'
        )
        return page.encode("utf-8")


# --- Word -------------------------------------------------------------------------------------------------

_ACCENT = "2F5BEA"
_NAVY = "1E3A8A"
_GRAY = "64748B"
_INK = "0F172A"


class DocxCvExporter(CvExporter):
    key = "docx"
    label = "Word (.docx)"
    extension = "docx"

    def export(self, markdown: str) -> bytes:
        from docx import Document
        from docx.shared import Cm, Pt, RGBColor

        document = Document()
        for section in document.sections:
            section.top_margin = section.bottom_margin = Cm(1.6)
            section.left_margin = section.right_margin = Cm(1.8)
        normal = document.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(10.5)
        normal.paragraph_format.space_after = Pt(2)

        def runs(paragraph, text: str, size: float | None = None, color: str | None = None, italic: bool = False) -> None:
            for kind, value, url in tokens(text):
                if kind == "link":
                    _hyperlink(paragraph, url, value, size or 10.5)
                    continue
                run = paragraph.add_run(value)
                run.bold = kind == "bold"
                run.italic = italic or kind == "italic"
                if size:
                    run.font.size = Pt(size)
                if color:
                    run.font.color.rgb = RGBColor.from_string(color)

        in_header = False
        for block in parse(markdown):
            if block.kind == "h1":
                p = document.add_paragraph()
                run = p.add_run(block.text)
                run.bold, run.font.size = True, Pt(24)
                run.font.color.rgb = RGBColor.from_string(_INK)
                p.paragraph_format.space_after = Pt(0)
                in_header = True
            elif block.kind == "h2":
                in_header = False
                p = document.add_paragraph()
                p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(12), Pt(4)
                run = p.add_run(block.text.upper())
                run.bold, run.font.size = True, Pt(10.5)
                run.font.color.rgb = RGBColor.from_string(_NAVY)
                _bottom_border(p)
            elif block.kind == "h3":
                p = document.add_paragraph()
                p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(8), Pt(0)
                head, *links = [part.strip() for part in block.text.split("  ·  ")]
                run = p.add_run(head)
                run.bold, run.font.size = True, Pt(11)
                for link in links:
                    p.add_run("   ")
                    runs(p, link, 9.5)
            elif block.kind == "ul":
                for item in block.items:
                    p = document.add_paragraph(style="List Bullet")
                    p.paragraph_format.space_after = Pt(1)
                    runs(p, item)
            elif in_header:
                p = document.add_paragraph()
                headline = re.fullmatch(r"\*\*(.+)\*\*", block.text)
                if headline:
                    run = p.add_run(headline.group(1))
                    run.bold, run.font.size = True, Pt(12.5)
                    run.font.color.rgb = RGBColor.from_string(_ACCENT)
                else:
                    runs(p, block.text, 9.5, _GRAY)
            else:
                p = document.add_paragraph()
                if block.is_meta:
                    runs(p, block.text[1:-1], 9.5, _GRAY, italic=True)
                else:
                    runs(p, block.text)
        buffer = io.BytesIO()
        document.save(buffer)
        return buffer.getvalue()


def _bottom_border(paragraph) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for attr, value in (("w:val", "single"), ("w:sz", "8"), ("w:space", "2"), ("w:color", "C7D2FE")):
        bottom.set(qn(attr), value)
    borders.append(bottom)
    p_pr.append(borders)


def _hyperlink(paragraph, url: str, text: str, size: float) -> None:
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    if not url.startswith(("http://", "https://", "mailto:")):
        paragraph.add_run(text)
        return
    r_id = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), _ACCENT)
    font_size = OxmlElement("w:sz")
    font_size.set(qn("w:val"), str(int(size * 2)))
    props.extend([color, font_size])
    run.append(props)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


DEFAULT_EXPORTERS: tuple[CvExporter, ...] = (HtmlCvExporter(), DocxCvExporter())
