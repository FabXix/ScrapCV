"""Limpieza de textos de Canvas para que se lean como un CV y no como una lista de tareas."""
from __future__ import annotations

import re

from scrapcv.domain.skills import normalize

_MONTHS = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
_MINOR = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "en", "a", "al", "para", "por", "con", "sin",
          "sobre", "un", "una"}
_ACRONYMS = {"api", "apis", "rest", "sql", "ti", "tic", "uml", "poo", "ia", "ii", "iii", "iv", "vi", "vii", "i", "ui",
             "ux", "iot", "bd", "erp", "crm", "html", "css", "aws"}
_NUMBERED = re.compile(
    r"\b(?:lab(?:oratorio)?|tarea|actividad|pr[aá]ctica|entrega(?:ble)?|ejercicio|caso|casos|reto|sesi[oó]n(?:es)?|"
    r"unidad|parcial|semana|m[oó]dulo|avance|sprint|hito)\s*#?\d+(?:[.\-]\d+)*(?:\s*(?:,|y)\s*\d+)*\b",
    re.I,
)
_GENERIC_RE = re.compile(
    r"((primer|primera|segunda|segundo|tercer|tercera|ultima|ultimo)a? )?"
    r"(entrega|avance|trabajo|reporte|proyecto|evidencia)( (final|integrador|parcial))?"
    r"( (del?|de la|de tu|de su) (proyecto|materia|curso)( final)?)?"
)
# Canvas suele guardar los nombres en mayúsculas y sin acentos («ADMINISTRACION DE PROYECTOS»).
_ACCENTS = {
    "administracion": "administración", "gestion": "gestión", "agil": "ágil", "tecnologias": "tecnologías",
    "tecnologia": "tecnología", "programacion": "programación", "aplicacion": "aplicación",
    "aplicaciones": "aplicaciones", "informacion": "información", "ingenieria": "ingeniería",
    "comunicacion": "comunicación", "economia": "economía", "organizacion": "organización", "logica": "lógica",
    "matematicas": "matemáticas", "estadistica": "estadística", "metodologia": "metodología", "analisis": "análisis",
    "diseno": "diseño", "sintesis": "síntesis", "politica": "política", "practica": "práctica",
    "practicas": "prácticas", "teoria": "teoría", "investigacion": "investigación", "innovacion": "innovación",
    "electronica": "electrónica", "fisica": "física", "quimica": "química", "calculo": "cálculo",
    "algebra": "álgebra", "optimizacion": "optimización", "simulacion": "simulación", "computacion": "computación",
    "graficas": "gráficas", "numericos": "numéricos", "numerico": "numérico", "basicas": "básicas",
    "etica": "ética", "psicologia": "psicología", "mercadotecnia": "mercadotecnia", "publica": "pública",
    "economica": "económica", "juridica": "jurídica", "estrategica": "estratégica", "tecnicas": "técnicas",
    "tecnica": "técnica", "biologia": "biología", "dinamica": "dinámica", "mecanica": "mecánica",
}


def is_generic_title(name: str) -> bool:
    """«Primer entrega del proyecto final», «Avance 2»… no dicen de qué trata el proyecto."""
    text = re.sub(r"\s{2,}", " ", _NUMBERED.sub(" ", name)).strip(" .-–—:")
    return not text or bool(_GENERIC_RE.fullmatch(normalize(text))) or normalize(text) in _GENERIC
_GENERIC = {"proyecto", "proyecto final", "entrega final", "final", "entrega", "proyecto en equipo", "practica",
            "tarea", "proyecto integrador", "evidencia", "trabajo final"}


def _title_word(word: str, first: bool) -> str:
    low = word.lower()
    low = _ACCENTS.get(low, low)
    if low.strip("().,:") in _ACRONYMS:
        return word.upper()
    if not first and low in _MINOR:
        return low
    return low[:1].upper() + low[1:]


def pretty_course(name: str) -> str:
    """«DESARROLLO DE APLICACIONES WEB (O2025_ESI3124N)» → «Desarrollo de Aplicaciones Web»."""
    name = re.sub(r"\s*[\(\[][^)\]]*[\)\]]\s*$", "", name).strip() or name
    if name.isupper() or name.islower():
        name = " ".join(_title_word(w, i == 0) for i, w in enumerate(name.split()))
    return name


def pretty_name(name: str) -> str:
    """«FABRICIO RODRIGUEZ CASTRO» → «Fabricio Rodriguez Castro» (Canvas a veces lo guarda en mayúsculas)."""
    name = " ".join(name.split())
    if name.isupper() or name.islower():
        return " ".join(w.lower() if w.lower() in _MINOR and i else w[:1].upper() + w[1:].lower()
                        for i, w in enumerate(name.split()))
    return name


def clean_title(assignment_name: str) -> str:
    """«MongoDB Lab 2 - MongoDB con una REST API» → «MongoDB con una REST API»."""
    text = _NUMBERED.sub(" ", assignment_name)
    parts = [re.sub(r"\s{2,}", " ", p).strip(" .-–—:") for p in re.split(r"\s+[-–—|]\s+|:\s*", text)]
    parts = [p for p in parts if p and normalize(p) not in _GENERIC and not _GENERIC_RE.fullmatch(normalize(p))]
    parts = [p for p in parts if not any(p != q and normalize(p) in normalize(q) for q in parts)]
    title = " — ".join(dict.fromkeys(parts))
    if not title:
        return assignment_name.strip()
    return title[:1].upper() + title[1:]


def month_year(iso: str) -> str:
    match = re.match(r"(\d{4})-(\d{2})", iso or "")
    if not match:
        return ""
    month = int(match.group(2))
    return f"{_MONTHS[month - 1]} {match.group(1)}" if 1 <= month <= 12 else match.group(1)


def display_url(value: str) -> str:
    return re.sub(r"^(https?://)?(www\.)?", "", value.strip()).rstrip("/")


def full_url(value: str) -> str:
    value = value.strip()
    return value if value.startswith(("http://", "https://")) else f"https://{value}"


def join_es(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]
