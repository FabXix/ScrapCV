"""Configuración del usuario y fuentes del token (CAR-01).

- Las preferencias van en ~/.scrapcv/config.json (sin el token).
- El token va en el llavero del sistema operativo (`keyring`: Administrador de
  credenciales en Windows, Llavero en macOS, Secret Service en Linux), nunca en
  un archivo de texto ni en el repositorio (sección 4.5).
- Si una versión anterior dejó el token en config.json, se mueve al llavero y se
  borra del archivo la primera vez que se carga la configuración.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scrapcv.domain.models import ContactInfo
from scrapcv.ports import SecretStore, TokenProvider

log = logging.getLogger("scrapcv.config")

TOKEN_ENV_VAR = "CANVAS_TOKEN"
DEFAULT_CONFIG_PATH = Path.home() / ".scrapcv" / "config.json"
KEYRING_SERVICE = "ScrapCV"
KEYRING_USER = "canvas_token"
_LEGACY_TOKEN_KEY = "canvas_token"


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
    degree: str = ""
    institution: str = ""
    period: str = ""
    last_posting: str = ""  # la última vacante pegada, para no perderla al cerrar
    template_key: str = "proyectos"

    def contact(self) -> ContactInfo:
        return ContactInfo(self.phone, self.location, self.linkedin, self.github, self.portfolio,
                           self.degree, self.institution, self.period)


# --- Secretos --------------------------------------------------------------------------------------

class KeyringSecretStore(SecretStore):
    """Token en el llavero del sistema operativo."""

    def __init__(self, service: str = KEYRING_SERVICE, user: str = KEYRING_USER) -> None:
        self._service, self._user = service, user
        try:
            import keyring
            from keyring.backends import fail

            self._keyring = None if isinstance(keyring.get_keyring(), fail.Keyring) else keyring
        except ImportError:
            self._keyring = None

    @property
    def available(self) -> bool:
        return self._keyring is not None

    def get(self) -> str | None:
        if not self._keyring:
            return None
        try:
            return self._keyring.get_password(self._service, self._user) or None
        except Exception as exc:  # backend del sistema no disponible
            log.warning("No se pudo leer el llavero: %s", exc.__class__.__name__)
            return None

    def set(self, value: str) -> None:
        if not self._keyring:
            raise RuntimeError("No hay un llavero disponible: instala «keyring» (pip install keyring) para recordar el token.")
        self._keyring.set_password(self._service, self._user, value)

    def delete(self) -> None:
        if not self._keyring:
            return
        try:
            self._keyring.delete_password(self._service, self._user)
        except Exception:  # no había token guardado
            pass


class MemorySecretStore(SecretStore):
    """Para pruebas: no persiste nada."""

    def __init__(self, value: str | None = None) -> None:
        self._value = value

    @property
    def available(self) -> bool:
        return True

    def get(self) -> str | None:
        return self._value

    def set(self, value: str) -> None:
        self._value = value

    def delete(self) -> None:
        self._value = None


# --- Preferencias ------------------------------------------------------------------------------------

class SettingsStore:
    """Guarda las preferencias en JSON local; el token se delega al `SecretStore`."""

    def __init__(self, path: Path = DEFAULT_CONFIG_PATH, secrets: SecretStore | None = None) -> None:
        self._path = path
        self._secrets = secrets or KeyringSecretStore()
        self._migrate_legacy_token()

    @property
    def can_remember_token(self) -> bool:
        return self._secrets.available

    def load(self) -> Settings:
        data = self._read()
        known = {k: v for k, v in data.get("settings", {}).items() if k in Settings.__dataclass_fields__}
        return Settings(**known)

    def save(self, settings: Settings) -> None:
        data = self._read()
        data["settings"] = asdict(settings)
        data.pop(_LEGACY_TOKEN_KEY, None)
        self._write(data)

    def save_token(self, token: str) -> None:
        self._secrets.set(token)

    def forget_token(self) -> None:
        self._secrets.delete()

    def stored_token(self) -> str | None:
        return self._secrets.get()

    def _migrate_legacy_token(self) -> None:
        data = self._read()
        legacy = data.get(_LEGACY_TOKEN_KEY)
        if not legacy:
            return
        if not self._secrets.available:
            log.warning("config.json tiene un token en texto plano y no hay llavero para moverlo; instala «keyring».")
            return
        self._secrets.set(legacy)
        del data[_LEGACY_TOKEN_KEY]
        self._write(data)
        log.info("El token se movió de config.json al llavero del sistema.")

    def _read(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        """Escritura atómica; el archivo nace con permisos de solo-dueño (no se corrigen después)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)


# --- Proveedores de token ------------------------------------------------------------------------------

class EnvTokenProvider(TokenProvider):
    def __init__(self, var: str = TOKEN_ENV_VAR) -> None:
        self._var = var

    def get_token(self) -> str | None:
        return os.environ.get(self._var) or None


class StoredTokenProvider(TokenProvider):
    """Token recordado en el llavero."""

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
