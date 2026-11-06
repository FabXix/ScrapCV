"""Configuración del usuario y fuentes del token (CAR-01).

El token vive en una variable de entorno o en ~/.scrapcv/config.json,
fuera del repositorio y nunca en el código (sección 4.5).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scrapcv.ports import TokenProvider

TOKEN_ENV_VAR = "CANVAS_TOKEN"
DEFAULT_CONFIG_PATH = Path.home() / ".scrapcv" / "config.json"


@dataclass
class Settings:
    canvas_url: str = "https://canvas.iteso.mx"
    data_dir: str = str(Path.cwd() / "data")
    use_demo: bool = True
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = ""
    use_llm: bool = True
    excluded_courses: list[str] = field(default_factory=list)
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""


class SettingsStore:
    """Guarda las preferencias (sin el token) en un archivo JSON local."""

    def __init__(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        self._path = path

    def load(self) -> Settings:
        data = self._read()
        known = {k: v for k, v in data.get("settings", {}).items() if k in Settings.__dataclass_fields__}
        return Settings(**known)

    def save(self, settings: Settings) -> None:
        data = self._read()
        data["settings"] = asdict(settings)
        self._write(data)

    def save_token(self, token: str) -> None:
        data = self._read()
        data["canvas_token"] = token
        self._write(data)

    def stored_token(self) -> str | None:
        return self._read().get("canvas_token") or None

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(self._path, 0o600)  # solo el dueño puede leer el token
        except OSError:
            pass


class EnvTokenProvider(TokenProvider):
    def __init__(self, var: str = TOKEN_ENV_VAR) -> None:
        self._var = var

    def get_token(self) -> str | None:
        return os.environ.get(self._var) or None


class FileTokenProvider(TokenProvider):
    def __init__(self, store: SettingsStore) -> None:
        self._store = store

    def get_token(self) -> str | None:
        return self._store.stored_token()


class StaticTokenProvider(TokenProvider):
    """Token escrito en la interfaz durante esta sesión (no se persiste)."""

    def __init__(self, token: str | None) -> None:
        self._token = (token or "").strip() or None

    def get_token(self) -> str | None:
        return self._token


class ChainedTokenProvider(TokenProvider):
    """Devuelve el primer token disponible en el orden dado."""

    def __init__(self, *providers: TokenProvider) -> None:
        self._providers = providers

    def get_token(self) -> str | None:
        for provider in self._providers:
            token = provider.get_token()
            if token:
                return token
        return None
