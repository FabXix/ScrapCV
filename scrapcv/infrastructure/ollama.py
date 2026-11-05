"""Adaptador de Ollama como `LanguageModel`.

Restricción de privacidad (sección 6.1): solo acepta un servidor en la propia
máquina. Si alguien configura una URL remota, se rechaza en el constructor.
"""
from __future__ import annotations

import ipaddress
import json
import socket
from urllib.parse import urlparse

import requests

from scrapcv.ports import LanguageModel


class RemoteModelRejected(ValueError):
    pass


class LanguageModelError(RuntimeError):
    pass


def _is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(socket.gethostbyname(host)).is_loopback
    except (OSError, ValueError):
        return False


class OllamaLanguageModel(LanguageModel):
    def __init__(self, base_url: str, model: str, timeout: float = 600.0, session: requests.Session | None = None) -> None:
        host = urlparse(base_url).hostname or ""
        if not _is_loopback(host):
            raise RemoteModelRejected("Ollama debe correr en esta computadora (localhost).")
        self._base = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._session = session or requests.Session()

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

    def is_available(self) -> bool:
        return self._model in self.list_models()

    def list_models(self) -> list[str]:
        try:
            response = self._session.get(f"{self._base}/api/tags", timeout=5)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except (requests.RequestException, ValueError, KeyError):
            return []

    def complete_json(self, system: str, prompt: str) -> dict:
        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        try:
            response = self._session.post(f"{self._base}/api/chat", json=payload, timeout=self._timeout)
            response.raise_for_status()
            content = response.json()["message"]["content"]
            data = json.loads(content)
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise LanguageModelError(f"Ollama no respondió correctamente: {exc.__class__.__name__}") from exc
        if not isinstance(data, dict):
            raise LanguageModelError("La respuesta del modelo no es un objeto JSON.")
        return data
