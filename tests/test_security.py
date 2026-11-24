"""Observaciones de seguridad: token de Canvas, archivos comprimidos y datos guardados."""
import json
import subprocess
from pathlib import Path

import pytest

from scrapcv.extraction.base import ExtractionContext
from scrapcv.extraction.extractors import archives
from scrapcv.extraction.extractors.archives import ArchiveLimits, SevenZipExtractor, UnsafeArchive
from scrapcv.infrastructure.canvas.http_client import CanvasHttpClient, CanvasHttpError, InsecureCanvasUrl
from scrapcv.infrastructure.config import MemorySecretStore, Settings, SettingsStore
from scrapcv.infrastructure.storage import CorruptDataError, DataLayout, JsonIndexRepository


class _Response:
    def __init__(self, status, payload=None, links=None):
        self.status_code, self._payload, self.links, self.headers, self.text = status, payload, links or {}, {}, ""

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self._responses, self.calls = list(responses), []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._responses.pop(0)


# --- Token de Canvas -----------------------------------------------------------------------------------

@pytest.mark.parametrize("url", ["http://canvas.iteso.mx", "canvas.iteso.mx", "ftp://canvas.iteso.mx"])
def test_canvas_url_must_be_https(url):
    with pytest.raises(InsecureCanvasUrl):
        CanvasHttpClient(url, "tok")


def test_pagination_never_sends_token_to_another_host():
    session = _Session([_Response(200, [{"id": 1}], {"next": {"url": "https://atacante.example/api/v1/x?page=2"}})])
    client = CanvasHttpClient("https://canvas.iteso.mx", "tok", session=session)
    with pytest.raises(CanvasHttpError):
        list(client.get_paginated("x"))
    assert len(session.calls) == 1  # la segunda página nunca se pidió


def test_pagination_rejects_downgrade_to_http():
    session = _Session([_Response(200, [], {"next": {"url": "http://canvas.iteso.mx/api/v1/x?page=2"}})])
    with pytest.raises(CanvasHttpError):
        list(CanvasHttpClient("https://canvas.iteso.mx", "tok", session=session).get_paginated("x"))


def test_absolute_urls_to_other_hosts_are_not_authenticated():
    session = _Session([])
    with pytest.raises(CanvasHttpError):
        CanvasHttpClient("https://canvas.iteso.mx", "tok", session=session).get_json("https://otro.example/x")
    assert session.calls == []


def test_token_lives_in_the_secret_store_not_in_config(tmp_path):
    path = tmp_path / "config.json"
    secrets = MemorySecretStore()
    store = SettingsStore(path, secrets)
    store.save(Settings(phone="123"))
    store.save_token("7~secreto")
    assert "7~secreto" not in path.read_text("utf-8")
    assert store.stored_token() == "7~secreto"


def test_plaintext_token_from_older_versions_is_migrated(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"settings": {}, "canvas_token": "7~viejo"}), "utf-8")
    secrets = MemorySecretStore()
    SettingsStore(path, secrets)
    assert secrets.get() == "7~viejo"
    assert "7~viejo" not in path.read_text("utf-8")


# --- Archivos comprimidos ----------------------------------------------------------------------------------

_LISTING = """
7-Zip 23.01

Listing archive: bomba.7z

--
Path = bomba.7z
Type = 7z

----------
Path = carpeta
Folder = +
Size = 0

Path = carpeta/enorme.bin
Folder = -
Size = {size}
Attributes = A_ -rw-r--r--
"""


def _fake_7z(monkeypatch, listing, extracted=None):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1] == "l":
            return subprocess.CompletedProcess(cmd, 0, stdout=listing, stderr="")
        if extracted:
            target = Path(cmd[3][2:])
            for name, data in extracted.items():
                (target / name).parent.mkdir(parents=True, exist_ok=True)
                (target / name).write_bytes(data)
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(archives.subprocess, "run", run)
    return calls


def _ctx(tmp_path):
    return ExtractionContext(base=tmp_path, label_prefix="", work_dir=tmp_path / "work")


def test_7z_respects_the_same_zip_bomb_limits(tmp_path, monkeypatch):
    archive = tmp_path / "bomba.7z"
    archive.write_bytes(b"0" * 1000)
    calls = _fake_7z(monkeypatch, _LISTING.format(size=10 * 1024 * 1024))
    with pytest.raises(UnsafeArchive):
        SevenZipExtractor(executable="7z").extract(archive, _ctx(tmp_path))
    assert all(cmd[1] == "l" for cmd in calls)  # nunca llegó a extraer


def test_7z_checks_what_was_really_written(tmp_path, monkeypatch):
    archive = tmp_path / "mentira.7z"
    archive.write_bytes(b"0" * 1000)
    _fake_7z(monkeypatch, _LISTING.format(size=10), {"carpeta/enorme.bin": b"x" * 500_000})
    with pytest.raises(UnsafeArchive):
        SevenZipExtractor(ArchiveLimits(max_ratio=50), executable="7z").extract(archive, _ctx(tmp_path))


def test_7z_rejects_symlinks(tmp_path, monkeypatch):
    archive = tmp_path / "link.7z"
    archive.write_bytes(b"0" * 1000)
    _fake_7z(monkeypatch, _LISTING.format(size=10).replace("A_ -rw-r--r--", "A_ lrwxrwxrwx"))
    with pytest.raises(UnsafeArchive):
        SevenZipExtractor(executable="7z").extract(archive, _ctx(tmp_path))


# --- Datos guardados ---------------------------------------------------------------------------------------

def test_corrupt_index_is_set_aside_and_stops_the_process(tmp_path):
    layout = DataLayout(tmp_path)
    layout.index_file.write_text('{"entries": [{"key": "a", ', "utf-8")
    with pytest.raises(CorruptDataError):
        JsonIndexRepository(layout)
    backups = list(tmp_path.glob("index.json.danado-*"))
    assert backups and backups[0].read_text("utf-8").startswith('{"entries"')  # nada se perdió
    assert not layout.index_file.exists()


def test_missing_index_still_starts_empty(tmp_path):
    assert JsonIndexRepository(DataLayout(tmp_path)).all() == []
