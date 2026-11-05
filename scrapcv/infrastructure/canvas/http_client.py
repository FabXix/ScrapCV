"""Cliente HTTP para la API REST de Canvas.

Responsabilidad única: hablar HTTP respetando las reglas de la API
(paginación por cabecera Link, límite de tasa y reintentos con espera, CAR-06).
No sabe nada de materias ni de entregas.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlparse

import requests

log = logging.getLogger("scrapcv.canvas.http")


class CanvasAuthError(Exception):
    """El token no es válido o no tiene permisos."""


class CanvasHttpError(Exception):
    pass


class CanvasHttpClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        session: requests.Session | None = None,
        max_retries: int = 5,
        backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 60.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._session = session or requests.Session()
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self._sleep = sleep
        self._timeout = timeout

    # --- API pública -----------------------------------------------------
    def get_json(self, path: str, params: dict | list | None = None) -> object:
        return self._request(self._url(path), params).json()

    def get_paginated(self, path: str, params: dict | list | None = None) -> Iterator[dict]:
        url: str | None = self._url(path)
        query = params
        while url:
            response = self._request(url, query)
            payload = response.json()
            yield from payload if isinstance(payload, list) else [payload]
            url = response.links.get("next", {}).get("url")
            query = None  # la URL "next" ya trae los parámetros

    def download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".part")
        response = self._request(url, None, stream=True, authenticate=self._is_canvas_host(url))
        with tmp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                handle.write(chunk)
        tmp.replace(destination)  # atómico: una descarga cortada no deja un archivo "completo"

    # --- Detalles ----------------------------------------------------------
    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self._base}/api/v1/{path.lstrip('/')}"

    def _is_canvas_host(self, url: str) -> bool:
        return urlparse(url).netloc == urlparse(self._base).netloc

    def _request(self, url: str, params, stream: bool = False, authenticate: bool = True) -> requests.Response:
        headers = {"Authorization": f"Bearer {self._token}"} if authenticate else {}
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.get(url, params=params, headers=headers, stream=stream, timeout=self._timeout)
            except requests.RequestException as exc:
                if attempt == self._max_retries:
                    raise CanvasHttpError(f"Fallo de red: {exc.__class__.__name__}") from exc
                self._wait(attempt, None)
                continue

            if response.status_code == 401:
                raise CanvasAuthError("Token inválido o expirado (401).")
            if self._is_throttled(response):
                if attempt == self._max_retries:
                    raise CanvasHttpError("Límite de solicitudes de Canvas excedido tras varios reintentos.")
                log.warning("Límite de tasa alcanzado; esperando antes de reintentar.")
                self._wait(attempt, response.headers.get("Retry-After"))
                continue
            if response.status_code >= 500 and attempt < self._max_retries:
                self._wait(attempt, None)
                continue
            if response.status_code >= 400:
                raise CanvasHttpError(f"HTTP {response.status_code} en {urlparse(url).path}")
            return response
        raise CanvasHttpError("Sin respuesta")  # pragma: no cover

    @staticmethod
    def _is_throttled(response: requests.Response) -> bool:
        if response.status_code == 429:
            return True
        return response.status_code == 403 and "rate limit" in response.text.lower()

    def _wait(self, attempt: int, retry_after: str | None) -> None:
        try:
            delay = float(retry_after) if retry_after else self._backoff * (2**attempt)
        except ValueError:
            delay = self._backoff * (2**attempt)
        self._sleep(min(delay, 60.0))
