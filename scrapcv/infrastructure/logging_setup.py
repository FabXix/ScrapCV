"""Registros de la aplicación con censura de secretos (CAR-01, sección 7.1 Seguridad)."""
from __future__ import annotations

import logging
import re
from pathlib import Path

_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9~._\-]+", re.IGNORECASE)
_TOKEN_PARAM = re.compile(r"(access_token=)[^&\s]+", re.IGNORECASE)


class SecretRedactingFilter(logging.Filter):
    """Sustituye los secretos conocidos y los patrones de token antes de escribir."""

    def __init__(self) -> None:
        super().__init__()
        self._secrets: set[str] = set()

    def register(self, secret: str | None) -> None:
        if secret and len(secret) >= 6:
            self._secrets.add(secret)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        text = _BEARER.sub(r"\1***", text)
        return _TOKEN_PARAM.sub(r"\1***", text)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(record.getMessage())
        record.args = ()
        return True


REDACTOR = SecretRedactingFilter()


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("scrapcv")
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.FileHandler(log_dir / "scrapcv.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(REDACTOR)
    root.addHandler(handler)
