"""Controlador de la interfaz: guarda la configuración y construye la fachada.

Recibe por inyección la función que arma la aplicación (`app_factory`), así
la interfaz puede probarse con una fachada falsa (DIP).
"""
from __future__ import annotations

from typing import Callable

from scrapcv.application.facade import ScrapCvFacade
from scrapcv.infrastructure.config import (
    ChainedTokenProvider,
    EnvTokenProvider,
    FileTokenProvider,
    Settings,
    SettingsStore,
    StaticTokenProvider,
)
from scrapcv.ranking.roles import JobRole

AppFactory = Callable[[Settings, str | None], ScrapCvFacade]


class AppController:
    def __init__(self, store: SettingsStore, app_factory: AppFactory, models_lister: Callable[[Settings], list[str]]) -> None:
        self._store = store
        self._factory = app_factory
        self._list_models = models_lister
        self.settings = store.load()
        self._typed_token: str | None = None
        self._app: ScrapCvFacade | None = None

    # --- Configuración -------------------------------------------------------------
    def has_saved_token(self) -> bool:
        return bool(FileTokenProvider(self._store).get_token() or EnvTokenProvider().get_token())

    def apply(self, settings: Settings, typed_token: str | None, remember_token: bool) -> ScrapCvFacade:
        self.settings = settings
        self._typed_token = (typed_token or "").strip() or None
        if remember_token and self._typed_token:
            self._store.save_token(self._typed_token)
        self._store.save(settings)
        token = ChainedTokenProvider(
            StaticTokenProvider(self._typed_token), EnvTokenProvider(), FileTokenProvider(self._store)
        ).get_token()
        self._app = self._factory(settings, token)
        return self._app

    def available_models(self, settings: Settings) -> list[str]:
        return self._list_models(settings)

    @property
    def app(self) -> ScrapCvFacade:
        if self._app is None:
            self._app = self.apply(self.settings, None, False)
        return self._app

    # --- Puesto ------------------------------------------------------------------------
    def resolve_role(self, name: str, keywords: str) -> JobRole:
        role = self.app.roles.get(name)
        if role:
            return role
        if not keywords.strip():
            raise ValueError("Para un puesto personalizado escribe palabras clave (p. ej. «python, sql, api»).")
        return JobRole.custom(name, keywords)
