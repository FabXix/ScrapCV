"""Criterios de aceptación de la sección 7.2, contra el Canvas simulado."""
import json

import pytest

from scrapcv.domain.models import Stage, StageStatus
from scrapcv.infrastructure.canvas.http_client import CanvasAuthError, CanvasHttpClient
from scrapcv.infrastructure.logging_setup import SecretRedactingFilter
from scrapcv.infrastructure.ollama import OllamaLanguageModel, RemoteModelRejected
from scrapcv.ranking.ranker import SelectionCriteria


def test_one_action_downloads_and_organizes_everything(processed_app):
    """7.2-1 y CAR-05: data/raw/<materia>/<tarea>/ con nombres estables."""
    raw = processed_app.data_dir / "raw"
    assert (raw / "poo-2025o_101" / "proyecto-final-sistema-de-inventario_1001" / "inventario.zip").exists()
    meta = json.loads((raw / "poo-2025o_101" / "proyecto-final-sistema-de-inventario_1001" / "submission.json").read_text("utf-8"))
    assert meta["calificacion"] == "95" and meta["comentarios_profesor"]
    assert "url" not in json.dumps(meta["adjuntos"])  # sin URL firmadas


def test_every_entry_has_facts_or_is_marked(processed_app):
    """7.2-2 y CAR-31: lo ilegible queda marcado y un error no detiene nada."""
    for entry in processed_app.entries():
        if entry.stage(Stage.INGEST).status == StageStatus.ERROR:
            assert entry.stage(Stage.INGEST).reasons  # enlace caído con su motivo
            continue
        assert processed_app.facts(entry.key) is not None
    statuses = {e.assignment_name: e.stage(Stage.EXTRACT).status for e in processed_app.entries()}
    assert statuses["Reporte de laboratorio escaneado"] == StageStatus.FLAGGED


def test_cv_changes_with_role_and_is_traceable(processed_app):
    """7.2-3 y 7.2-4."""
    criteria = SelectionCriteria(max_projects=2)
    backend = processed_app.generate_cv(processed_app.roles.get("Prácticas de desarrollo backend"), criteria)
    data = processed_app.generate_cv(processed_app.roles.get("Prácticas de ciencia de datos"), criteria)
    assert backend.ranked[0].candidate.entry.key != data.ranked[0].candidate.entry.key
    for line in backend.markdown.splitlines():
        if line.startswith("- ") and "Evidencia" not in line:
            pytest.fail(f"viñeta sin evidencia: {line}")


def test_rerun_resumes_without_downloading_again(processed_app):
    summary = processed_app.ingest()
    assert summary.downloaded == 0 and summary.reused > 0


def test_token_never_reaches_disk(tmp_path, processed_app):
    redactor = SecretRedactingFilter()
    redactor.register("7~SuperSecretToken123")
    assert "SuperSecret" not in redactor.redact("Authorization: Bearer 7~SuperSecretToken123")
    for path in processed_app.data_dir.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".md", ".log"):
            assert "DB_PASSWORD" not in path.read_text("utf-8", errors="ignore")


def test_remote_ollama_is_rejected():
    """Privacidad (6.1): el modelo solo puede correr en la máquina del usuario."""
    with pytest.raises(RemoteModelRejected):
        OllamaLanguageModel("https://api.ejemplo.com", "x")


class _Response:
    def __init__(self, status, payload=None, links=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.links = links or {}
        self.headers = headers or {}
        self.text = "Rate Limit Exceeded" if status == 403 else ""

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._responses.pop(0)


def test_http_client_paginates_and_retries_on_throttle():
    """CAR-06: paginación por Link y espera ante límite de tasa."""
    session = _Session([
        _Response(403),
        _Response(200, [{"id": 1}], {"next": {"url": "https://c/api/v1/x?page=2"}}),
        _Response(200, [{"id": 2}]),
    ])
    waits = []
    client = CanvasHttpClient("https://c", "tok", session=session, sleep=waits.append)
    assert [item["id"] for item in client.get_paginated("x")] == [1, 2]
    assert len(waits) == 1


def test_http_client_reports_bad_token():
    client = CanvasHttpClient("https://c", "tok", session=_Session([_Response(401)]), sleep=lambda _s: None)
    with pytest.raises(CanvasAuthError):
        client.get_json("users/self")


def test_downloads_to_other_hosts_do_not_send_token(tmp_path):
    class _Stream(_Response):
        def iter_content(self, chunk_size):
            yield b"datos"

    session = _Session([_Stream(200)])
    CanvasHttpClient("https://canvas.iteso.mx", "tok", session=session).download("https://s3.amazonaws.com/f", tmp_path / "f")
    assert "Authorization" not in session.calls[0][1]["headers"]
    assert (tmp_path / "f").read_bytes() == b"datos"
