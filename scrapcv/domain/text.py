"""Utilidades de texto puras usadas por varias capas."""
from __future__ import annotations

import re
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"\d")
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def slugify(value: str, max_len: int = 60) -> str:
    """Nombre estable y seguro para carpetas (CAR-05)."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = _NON_SLUG.sub("-", normalized.lower()).strip("-")
    return (slug[:max_len].rstrip("-")) or "sin-nombre"


def contains_digits(value: str) -> bool:
    return bool(_DIGITS.search(value))


def strip_html(value: str) -> str:
    return _SPACES.sub(" ", _TAGS.sub(" ", value)).strip()


def tokenize(value: str) -> set[str]:
    """Tokens normalizados (minúsculas, sin acentos) para comparar palabras clave."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return {tok for tok in re.split(r"[^a-z0-9+#.]+", normalized) if len(tok) > 1}


# Palabras que aparecen en cualquier vacante y no distinguen un requisito de otro.
_STOP = {
    "para", "como", "with", "and", "the", "con", "sobre", "desde", "entre", "hacia", "cada", "todo", "todos", "toda",
    "conocimiento", "conocimientos", "experiencia", "manejo", "capacidad", "habilidad", "habilidades", "nivel",
    "basico", "basicos", "avanzado", "intermedio", "deseable", "indispensable", "requisito", "requisitos", "minimo",
    "buen", "buena", "buenas", "excelente", "solido", "solida", "uso", "area", "areas", "estudiante", "estudiantes",
    "carrera", "afines", "afin", "relacionadas", "relacionados", "trabajo", "proyectos", "proyecto", "empresa",
}


def significant_stems(value: str) -> set[str]:
    """Raíces de las palabras con contenido («Análisis financiero» → {"analis", "financ"})."""
    return {tok[:6] for tok in tokenize(value) if len(tok) >= 4 and tok not in _STOP and not tok.isdigit()}


def phrase_matches(phrase: str, corpus: str, threshold: float = 0.5) -> bool:
    """¿El texto menciona la mayoría de las palabras con contenido de la frase? Tolera plurales y conjugaciones."""
    wanted = significant_stems(phrase)
    if not wanted:
        return False
    have = significant_stems(corpus)
    return len(wanted & have) / len(wanted) >= threshold
