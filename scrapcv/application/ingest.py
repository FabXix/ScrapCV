"""Etapa 1: ingesta y descarga (CAR-02 a CAR-07, CAR-31)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from scrapcv.domain.models import IndexEntry, Stage, StageStatus, Submission
from scrapcv.ports import (
    AttachmentDownloader,
    CanvasReader,
    IndexRepository,
    NullProgress,
    ProgressListener,
    RawEvidenceStore,
    UserRepository,
)

log = logging.getLogger("scrapcv.ingest")
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    return _FORBIDDEN.sub("_", base).strip(" .") or "archivo"


@dataclass
class IngestSummary:
    courses: int = 0
    submissions: int = 0
    downloaded: int = 0
    reused: int = 0
    errors: int = 0


class IngestService:
    def __init__(
        self,
        reader: CanvasReader,
        downloader: AttachmentDownloader,
        raw_store: RawEvidenceStore,
        index: IndexRepository,
        users: UserRepository,
    ) -> None:
        self._reader = reader
        self._downloader = downloader
        self._raw = raw_store
        self._index = index
        self._users = users

    def run(self, progress: ProgressListener = NullProgress()) -> IngestSummary:
        summary = IngestSummary()
        user = self._reader.current_user()  # también valida el token (CAR-01)
        self._users.save(user)
        progress.info(f"Conectado como {user.name}.")
        courses = self._reader.list_courses()
        summary.courses = len(courses)
        progress.info(f"{len(courses)} materias encontradas (activas y completadas).")
        for number, course in enumerate(courses, start=1):
            progress.progress(number - 1, len(courses))
            try:
                submissions = [s for s in self._reader.list_submissions(course) if s.has_evidence]
            except Exception as exc:  # una materia con error no detiene la ingesta
                summary.errors += 1
                progress.warning(f"No se pudieron listar las entregas de {course.name}: {exc}")
                log.warning("Error listando %s: %s", course.id, exc.__class__.__name__)
                continue
            progress.info(f"{course.name}: {len(submissions)} entregas con evidencia.")
            for submission in submissions:
                self._ingest_one(submission, summary, progress)
            self._index.save()  # guardado incremental: se puede reanudar
        progress.progress(len(courses), len(courses))
        self._index.save()
        return summary

    def _ingest_one(self, sub: Submission, summary: IngestSummary, progress: ProgressListener) -> None:
        summary.submissions += 1
        previous = self._index.get(sub.key)
        entry = IndexEntry.from_submission(sub)
        if previous:
            entry.stages = previous.stages
        reasons: list[str] = []

        self._raw.write_json(sub.key, "submission.json", self._metadata(sub))
        if sub.body.strip():
            self._raw.write_text(sub.key, "texto_en_linea.html", sub.body)
        if sub.url.strip():
            self._raw.write_json(sub.key, "enlaces.json", [sub.url])

        folder = self._raw.folder_for(sub.key)
        used_names: set[str] = set()
        for attachment in sub.attachments:
            name = safe_filename(attachment.filename)
            if name in used_names:
                name = f"{attachment.id}_{name}"
            used_names.add(name)
            destination = folder / name
            if destination.exists() and (not attachment.size or destination.stat().st_size == attachment.size):
                summary.reused += 1  # reanudación: no se vuelve a descargar (sección 9.4)
                continue
            try:
                self._downloader.download(attachment.url, destination)
                summary.downloaded += 1
            except Exception as exc:  # CAR-31: se registra y se continúa
                summary.errors += 1
                reasons.append(f"{name}: no se pudo descargar ({exc.__class__.__name__})")
                progress.warning(f"{sub.assignment_name}: no se pudo descargar {name}.")

        if not reasons:
            status = StageStatus.OK
        elif len(reasons) < len(sub.attachments) or sub.body.strip() or sub.url.strip():
            status = StageStatus.PARTIAL
        else:
            status = StageStatus.ERROR
        entry.set_stage(Stage.INGEST, status, reasons)
        self._index.upsert(entry)

    @staticmethod
    def _metadata(sub: Submission) -> dict:
        """CAR-03. No se guardan las URL firmadas de los adjuntos."""
        return {
            "materia": sub.course.name,
            "codigo_materia": sub.course.code,
            "periodo": sub.course.term,
            "estado_materia": sub.course.state,
            "tarea": sub.assignment_name,
            "fecha_entrega": sub.submitted_at,
            "calificacion": sub.grade,
            "puntaje": sub.score,
            "puntos_posibles": sub.points_possible,
            "tipo": sub.submission_type,
            "trabajo_grupal": sub.is_group,
            "comentarios_profesor": [{"autor": c.author, "texto": c.text, "fecha": c.created_at} for c in sub.comments],
            "adjuntos": [{"nombre": a.filename, "tamano": a.size} for a in sub.attachments],
        }
