"""Puertos (interfaces) del sistema.

Las capas de aplicación dependen de estas abstracciones y nunca de una
implementación concreta (DIP). Cada interfaz es pequeña y con un solo
propósito (ISP): quien solo lee de Canvas no tiene que saber descargar, y
quien solo guarda hechos no tiene que saber de perfiles.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from scrapcv.domain.facts import Facts, ProjectProfile, TextSnippet
from scrapcv.domain.models import Course, IndexEntry, Submission, UserInfo


# --- Configuración ---------------------------------------------------------
class TokenProvider(ABC):
    """Fuente del token de acceso personal (CAR-01)."""

    @abstractmethod
    def get_token(self) -> str | None: ...


# --- Canvas ---------------------------------------------------------------
class CanvasReader(ABC):
    """Lectura de datos propios del estudiante desde Canvas."""

    @abstractmethod
    def current_user(self) -> UserInfo: ...

    @abstractmethod
    def list_courses(self) -> list[Course]: ...

    @abstractmethod
    def list_submissions(self, course: Course) -> list[Submission]: ...


class AttachmentDownloader(ABC):
    @abstractmethod
    def download(self, url: str, destination: Path) -> None: ...


# --- Progreso (Observer) ----------------------------------------------------
class ProgressListener(ABC):
    @abstractmethod
    def info(self, message: str) -> None: ...

    @abstractmethod
    def warning(self, message: str) -> None: ...

    @abstractmethod
    def progress(self, done: int, total: int) -> None: ...


class NullProgress(ProgressListener):
    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def progress(self, done: int, total: int) -> None:
        pass


# --- Persistencia -------------------------------------------------------------
class IndexRepository(ABC):
    """index.json: estado global de todas las entregas."""

    @abstractmethod
    def all(self) -> list[IndexEntry]: ...

    @abstractmethod
    def get(self, key: str) -> IndexEntry | None: ...

    @abstractmethod
    def upsert(self, entry: IndexEntry) -> None: ...

    @abstractmethod
    def save(self) -> None: ...


class RawEvidenceStore(ABC):
    """data/raw/<materia>/<tarea>/: evidencia tal como vino de Canvas."""

    @abstractmethod
    def folder_for(self, key: str) -> Path: ...

    @abstractmethod
    def write_json(self, key: str, name: str, data: object) -> None: ...

    @abstractmethod
    def write_text(self, key: str, name: str, text: str) -> None: ...


class AnalysisStore(ABC):
    """data/analysis/<materia>/<tarea>/: facts.json, contexto.json y perfil.json."""

    @abstractmethod
    def work_folder(self, key: str) -> Path: ...

    @abstractmethod
    def save_facts(self, facts: Facts) -> None: ...

    @abstractmethod
    def load_facts(self, key: str) -> Facts | None: ...

    @abstractmethod
    def save_snippets(self, key: str, snippets: list[TextSnippet]) -> None: ...

    @abstractmethod
    def load_snippets(self, key: str) -> list[TextSnippet]: ...

    @abstractmethod
    def save_profile(self, profile: ProjectProfile) -> None: ...

    @abstractmethod
    def load_profile(self, key: str) -> ProjectProfile | None: ...


class UserRepository(ABC):
    """Datos básicos del estudiante (nombre y correo) para el encabezado del CV."""

    @abstractmethod
    def save(self, user: UserInfo) -> None: ...

    @abstractmethod
    def load(self) -> UserInfo | None: ...


class CvRepository(ABC):
    @abstractmethod
    def save_draft(self, role_slug: str, markdown: str) -> Path: ...

    @abstractmethod
    def save_final(self, role_slug: str, markdown: str) -> Path: ...

    @abstractmethod
    def load_draft(self, role_slug: str) -> str | None: ...


# --- Modelo de lenguaje -----------------------------------------------------
class LanguageModel(ABC):
    """Modelo local. La implementación debe garantizar que no sale de la máquina."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def complete_json(self, system: str, prompt: str) -> dict: ...


class ProjectProfiler(ABC):
    """Estrategia para resumir un proyecto (CAR-20)."""

    @abstractmethod
    def profile(self, entry: IndexEntry, facts: Facts, snippets: Iterable[TextSnippet]) -> ProjectProfile: ...
