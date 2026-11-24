"""Persistencia en el sistema de archivos local.

Estructura (sección 4.1):
    data/raw/<materia>/<tarea>/          evidencia descargada
    data/analysis/<materia>/<tarea>/     facts.json, contexto.json, perfil.json, unpacked/
    data/index.json                      índice global
    data/cv/                             borradores y CV final
Cada etapa lee la salida de la anterior desde disco, así puede repetirse sola.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from scrapcv.domain.facts import Facts, ProjectProfile, TextSnippet
from scrapcv.domain.models import IndexEntry, UserInfo
from scrapcv.ports import AnalysisStore, CvRepository, IndexRepository, RawEvidenceStore, UserRepository


class CorruptDataError(RuntimeError):
    """Un archivo de datos existe pero no se puede leer. Se aparta y el proceso se detiene."""


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _write_json_atomic(path: Path, data: object) -> None:
    _write_bytes_atomic(path, json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))


def _quarantine(path: Path, reason: str) -> CorruptDataError:
    backup = path.with_name(f"{path.name}.danado-{datetime.now():%Y%m%d-%H%M%S}")
    os.replace(path, backup)
    return CorruptDataError(
        f"{path.name} está dañado ({reason}). Se apartó como {backup.name} para no perder datos; "
        "revísalo o vuelve a ejecutar la etapa que lo genera."
    )


def _read_json(path: Path, expected: type | None = None) -> object | None:
    """None solo si el archivo no existe. Si existe y está dañado, se aparta y se lanza CorruptDataError.

    Así un archivo dañado nunca se confunde con uno vacío: el siguiente save() no borra lo que había.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:  # JSON inválido o bytes que no son UTF-8
        raise _quarantine(path, "JSON inválido") from exc
    if expected is not None and not isinstance(data, expected):
        raise _quarantine(path, f"se esperaba {expected.__name__}")
    return data


class DataLayout:
    """Conoce las rutas; nadie más arma rutas a mano."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def analysis(self) -> Path:
        return self.root / "analysis"

    @property
    def index_file(self) -> Path:
        return self.root / "index.json"

    @property
    def cv(self) -> Path:
        return self.root / "cv"

    @property
    def logs(self) -> Path:
        return self.root / "logs"


class JsonIndexRepository(IndexRepository):
    def __init__(self, layout: DataLayout) -> None:
        self._path = layout.index_file
        data = _read_json(self._path, dict) or {}
        try:
            self._entries = {e["key"]: IndexEntry.from_dict(e) for e in data.get("entries", [])}
        except (KeyError, TypeError, ValueError) as exc:
            raise _quarantine(self._path, "entradas con formato inesperado") from exc

    def all(self) -> list[IndexEntry]:
        return sorted(self._entries.values(), key=lambda e: (e.course_name, e.assignment_name))

    def get(self, key: str) -> IndexEntry | None:
        return self._entries.get(key)

    def upsert(self, entry: IndexEntry) -> None:
        self._entries[entry.key] = entry

    def save(self) -> None:
        _write_json_atomic(self._path, {"version": 1, "entries": [e.to_dict() for e in self.all()]})


class FileRawEvidenceStore(RawEvidenceStore):
    def __init__(self, layout: DataLayout) -> None:
        self._layout = layout

    def folder_for(self, key: str) -> Path:
        folder = self._layout.raw / key
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def write_json(self, key: str, name: str, data: object) -> None:
        _write_json_atomic(self.folder_for(key) / name, data)

    def write_text(self, key: str, name: str, text: str) -> None:
        (self.folder_for(key) / name).write_text(text, encoding="utf-8")


class FileAnalysisStore(AnalysisStore):
    FACTS = "facts.json"
    SNIPPETS = "contexto.json"
    PROFILE = "perfil.json"

    def __init__(self, layout: DataLayout) -> None:
        self._layout = layout

    def work_folder(self, key: str) -> Path:
        folder = self._layout.analysis / key
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def save_facts(self, facts: Facts) -> None:
        _write_json_atomic(self.work_folder(facts.key) / self.FACTS, facts.to_dict())

    def load_facts(self, key: str) -> Facts | None:
        data = _read_json(self._layout.analysis / key / self.FACTS, dict)
        return Facts.from_dict(data) if data is not None else None

    def save_snippets(self, key: str, snippets: list[TextSnippet]) -> None:
        payload = [{"source": s.source, "text": s.text, "priority": s.priority} for s in snippets]
        _write_json_atomic(self.work_folder(key) / self.SNIPPETS, payload)

    def load_snippets(self, key: str) -> list[TextSnippet]:
        data = _read_json(self._layout.analysis / key / self.SNIPPETS, list) or []
        return [TextSnippet(**item) for item in data]

    def save_profile(self, profile: ProjectProfile) -> None:
        _write_json_atomic(self.work_folder(profile.key) / self.PROFILE, profile.to_dict())

    def load_profile(self, key: str) -> ProjectProfile | None:
        data = _read_json(self._layout.analysis / key / self.PROFILE, dict)
        return ProjectProfile.from_dict(data) if data is not None else None


class JsonUserRepository(UserRepository):
    def __init__(self, layout: DataLayout) -> None:
        self._path = layout.root / "usuario.json"

    def save(self, user: UserInfo) -> None:
        _write_json_atomic(self._path, {"id": user.id, "name": user.name, "email": user.email})

    def load(self) -> UserInfo | None:
        data = _read_json(self._path, dict)
        return UserInfo(**data) if data is not None else None


class FileCvRepository(CvRepository):
    def __init__(self, layout: DataLayout) -> None:
        self._dir = layout.cv

    def save_draft(self, role_slug: str, markdown: str) -> Path:
        return self._write(f"cv_{role_slug}.md", markdown)

    def save_final(self, role_slug: str, markdown: str) -> Path:
        return self._write(f"cv_{role_slug}_final.md", markdown)

    def load_draft(self, role_slug: str) -> str | None:
        path = self._dir / f"cv_{role_slug}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def save_evidence(self, role_slug: str, evidence: list[dict]) -> Path:
        path = self._dir / f"cv_{role_slug}.evidencia.json"
        _write_json_atomic(path, evidence)
        return path

    def save_export(self, role_slug: str, extension: str, data: bytes) -> Path:
        path = self._dir / f"cv_{role_slug}.{extension.lstrip('.')}"
        _write_bytes_atomic(path, data)
        return path

    def _write(self, name: str, markdown: str) -> Path:
        path = self._dir / name
        _write_bytes_atomic(path, markdown.encode("utf-8"))
        return path
