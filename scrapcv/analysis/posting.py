"""Lectura de la vacante: de texto libre a requisitos (`JobPosting`).

Mismo esquema que los perfiles de proyecto (Strategy + respaldo):
- `KeywordPostingAnalyzer`: sin modelo, con el catálogo de tecnologías.
- `LlmPostingAnalyzer`: el modelo separa requisitos, deseables y responsabilidades;
  todo lo que devuelve debe aparecer en el texto de la vacante (guarda anti-invención).
- `FallbackPostingAnalyzer`: intenta el primero y, si falla, usa el segundo.
"""
from __future__ import annotations

import logging
import re

from scrapcv.domain.posting import JobPosting
from scrapcv.domain.skills import canonical, find_in_text, is_soft, normalize
from scrapcv.domain.text import phrase_matches, significant_stems
from scrapcv.ports import LanguageModel, PostingAnalyzer

log = logging.getLogger("scrapcv.posting")

_TITLE = re.compile(r"^\s*(?:puesto|vacante|posici[oó]n|cargo|rol|job title)\s*[:\-–]\s*(.+)$", re.I)
_COMPANY = re.compile(r"^\s*(?:empresa|compa[nñ][ií]a|company)\s*[:\-–]\s*(.+)$", re.I)
_PREFERRED_HEADER = re.compile(r"\b(deseable|deseables|plus|valoramos|se valora|nice to have|preferente|bonus)\b", re.I)
_REQUIRED_HEADER = re.compile(r"\b(requisitos|requerimientos|indispensable|requirements|buscamos|perfil|conocimientos)\b", re.I)
_DUTIES_HEADER = re.compile(r"\b(responsabilidades|funciones|actividades|qu[eé] har[aá]s|responsibilities)\b", re.I)
_OTHER = re.compile(
    r"\b(ingl[eé]s|english|titulad|pasante|egresad|semestre|disponibilidad|horario|licencia|presencial|remoto|h[ií]brido|"
    r"edad|residencia|viajar|estudiante|licenciatura|carrera|afin|afín)\b", re.I)
_BULLET = re.compile(r"^\s*(?:[-•*·▪●]|\d+[.)])\s*")
_LEAD = re.compile(
    r"^(?:(?:amplios?|s[oó]lidos?|buenos?)\s+)?(?:conocimientos?|experiencia|manejo|dominio|habilidad(?:es)?|"
    r"capacidad|gusto|inter[eé]s|nociones)\s+(?:b[aá]sic[oa]s?\s+|intermedi[oa]s?\s+|avanzad[oa]s?\s+)?"
    r"(?:de|en|con|para|por|sobre)\s+", re.I)


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _short(line: str, limit: int = 90) -> str:
    line = _BULLET.sub("", line).strip(" .;:")
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


class KeywordPostingAnalyzer(PostingAnalyzer):
    @property
    def name(self) -> str:
        return "palabras clave"

    def analyze(self, text: str) -> JobPosting:
        lines = _lines(text)
        title, company = self._title(lines), ""
        required: list[str] = []
        preferred: list[str] = []
        duties: list[str] = []
        other: list[str] = []
        section = "intro"  # antes del primer encabezado solo cuentan tecnologías explícitas
        for line in lines:
            if (match := _COMPANY.match(line)) and not company:
                company = _short(match.group(1), 60)
                continue
            is_header = len(line) < 60 and not _BULLET.match(line)
            if is_header and _PREFERRED_HEADER.search(line):
                section = "preferred"
            elif is_header and _DUTIES_HEADER.search(line):
                section = "duties"
            elif is_header and _REQUIRED_HEADER.search(line):
                section = "required"
            if _OTHER.search(line):
                other.append(_short(line))
            skills = [s for s in find_in_text(line, include_soft=False)]
            if section == "duties" and _BULLET.match(line):
                duties.append(_short(line, 120))
            target = preferred if section == "preferred" or _PREFERRED_HEADER.search(line) else required
            target.extend(s.name for s in skills)
            generic = self._generic(line, is_header, skills)
            if generic and section in ("required", "preferred"):
                target.append(generic)
        soft = [s.name for s in find_in_text(text) if is_soft(s)]
        required = list(dict.fromkeys(required))
        preferred = [p for p in dict.fromkeys(preferred) if p not in required]
        return JobPosting(
            title=title, raw_text=text, company=company, required=tuple(required), preferred=tuple(preferred),
            soft_skills=tuple(dict.fromkeys(soft)), other=tuple(dict.fromkeys(other))[:6],
            responsibilities=tuple(duties[:6]), source=self.name,
        )

    @staticmethod
    def _generic(line: str, is_header: bool, skills: list) -> str | None:
        """Requisito que no es una tecnología del catálogo («Análisis financiero», «Redacción de reportes»)."""
        if is_header or skills or _OTHER.search(line) or len(line) > 90 or line.rstrip().endswith(":"):
            return None
        if any(is_soft(s) for s in find_in_text(line)):
            return None  # ya se cuenta como habilidad blanda
        phrase = _LEAD.sub("", _short(line, 90)).strip(" .;:")
        if not significant_stems(phrase) or len(phrase.split()) > 9:
            return None
        return phrase[:1].upper() + phrase[1:]

    @staticmethod
    def _title(lines: list[str]) -> str:
        for line in lines[:8]:
            if match := _TITLE.match(line):
                return _short(match.group(1), 70)
        for line in lines[:3]:
            if len(line.split()) <= 10 and not _BULLET.match(line):
                return _short(line, 70)
        return "Vacante"


POSTING_SYSTEM = (
    "Eres un reclutador técnico. Lees una vacante y separas lo que pide.\n"
    "Reglas estrictas:\n"
    "- Copia los requisitos tal como aparecen en la vacante; no agregues ninguno que no esté escrito.\n"
    "- «requisitos»: tecnologías, lenguajes, herramientas o conocimientos técnicos indispensables (nombres cortos).\n"
    "- «deseables»: tecnologías o conocimientos marcados como deseables, plus o valorados.\n"
    "- «habilidades_blandas»: habilidades interpersonales que menciona (trabajo en equipo, comunicación…).\n"
    "- «otros»: condiciones que no son habilidades (inglés, semestre, horario, modalidad).\n"
    "- «responsabilidades»: lo que hará la persona, frases cortas.\n"
    'Responde únicamente un objeto JSON: {"puesto": str, "empresa": str, "requisitos": [str], "deseables": [str], '
    '"habilidades_blandas": [str], "otros": [str], "responsabilidades": [str]}'
)


def _strings(value: object, limit: int = 15) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


class LlmPostingAnalyzer(PostingAnalyzer):
    """Usa el modelo para separar la vacante; se queda solo con lo que está escrito en ella."""

    def __init__(self, model: LanguageModel, keywords: PostingAnalyzer | None = None) -> None:
        self._model = model
        self._keywords = keywords or KeywordPostingAnalyzer()

    @property
    def name(self) -> str:
        return self._model.name

    def analyze(self, text: str) -> JobPosting:
        data = self._model.complete_json(POSTING_SYSTEM, f"VACANTE:\n{text.strip()}\n\nGenera el JSON.")
        corpus = " " + normalize(text) + " "
        base = self._keywords.analyze(text)

        def grounded(items: object) -> list[str]:
            kept = []
            for item in _strings(items):
                skill = canonical(item)
                forms = skill.forms if skill else (normalize(item),)
                if any(form and form in corpus for form in forms) or (not skill and phrase_matches(item, text, 0.6)):
                    kept.append(skill.name if skill else item)
                else:
                    log.info("Requisito descartado (no aparece en la vacante): %s", item)
            return kept

        required = list(dict.fromkeys(grounded(data.get("requisitos")) + list(base.required)))
        preferred = [p for p in dict.fromkeys(grounded(data.get("deseables")) + list(base.preferred)) if p not in required]
        soft = list(dict.fromkeys(grounded(data.get("habilidades_blandas")) + list(base.soft_skills)))
        title = str(data.get("puesto") or "").strip()
        company = str(data.get("empresa") or "").strip()
        return JobPosting(
            title=_short(title, 70) if title and normalize(title)[:12] in corpus else base.title,
            raw_text=text,
            company=company if company and normalize(company) in corpus else base.company,
            required=tuple(required), preferred=tuple(preferred), soft_skills=tuple(soft),
            other=tuple(grounded(data.get("otros")) or base.other)[:6],
            responsibilities=tuple(_short(r, 120) for r in _strings(data.get("responsabilidades"), 6)) or base.responsibilities,
            source=self.name,
        )


class FallbackPostingAnalyzer(PostingAnalyzer):
    def __init__(self, primary: PostingAnalyzer, fallback: PostingAnalyzer) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def name(self) -> str:
        return self._primary.name

    def analyze(self, text: str) -> JobPosting:
        try:
            posting = self._primary.analyze(text)
            if not posting.is_empty:
                return posting
        except Exception as exc:  # el modelo puede fallar de muchas formas; la vacante se lee igual
            log.warning("Lectura de vacante con modelo falló: %s", exc.__class__.__name__)
        return self._fallback.analyze(text)
