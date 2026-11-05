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
