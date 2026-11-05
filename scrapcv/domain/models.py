"""Entidades del dominio de ScrapCV.

Son objetos de datos sin dependencias de infraestructura: no saben de HTTP,
de disco ni de Tkinter. Todas las capas hablan en estos términos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from scrapcv.domain.text import slugify


class StageStatus(str, Enum):
    """Estado de una entrega dentro de una etapa del flujo."""

    PENDING = "pendiente"
    OK = "ok"
    PARTIAL = "parcial"  # se procesó, pero algo quedó marcado
    FLAGGED = "marcado"  # no hay contenido legible (escaneo, solo capturas, etc.)
    ERROR = "error"


class Stage(str, Enum):
    INGEST = "ingesta"
    EXTRACT = "extraccion"
    PROFILE = "perfil"


@dataclass(frozen=True)
class Course:
    id: int
    name: str
    code: str = ""
    term: str = ""
    state: str = "active"  # active | completed

    @property
    def slug(self) -> str:
        return f"{slugify(self.code or self.name)}_{self.id}"


@dataclass(frozen=True)
class Attachment:
    id: int
    filename: str
    url: str
    size: int = 0
    content_type: str = ""


@dataclass(frozen=True)
class Comment:
    author: str
    text: str
    created_at: str = ""


@dataclass(frozen=True)
class Submission:
    """Lo que el estudiante entregó en una tarea (no lo que pedía la tarea)."""

    id: int
    course: Course
    assignment_id: int
    assignment_name: str
    submitted_at: str = ""
    score: float | None = None
    grade: str | None = None
    points_possible: float | None = None
    submission_type: str = ""
    body: str = ""  # texto en línea (HTML)
    url: str = ""  # entrega tipo enlace
    attachments: tuple[Attachment, ...] = ()
    comments: tuple[Comment, ...] = ()
    is_group: bool = False

    @property
    def slug(self) -> str:
        return f"{slugify(self.assignment_name)}_{self.assignment_id}"

    @property
    def key(self) -> str:
        """Identificador estable de la entrega en todo el sistema."""
        return f"{self.course.slug}/{self.slug}"

    @property
    def has_evidence(self) -> bool:
        return bool(self.attachments or self.body.strip() or self.url.strip())


@dataclass
class StageResult:
    status: StageStatus = StageStatus.PENDING
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"status": self.status.value, "reasons": list(self.reasons)}

    @classmethod
    def from_dict(cls, data: dict) -> "StageResult":
        return cls(StageStatus(data.get("status", "pendiente")), list(data.get("reasons", [])))


@dataclass
class IndexEntry:
    """Fila de index.json: una entrega procesada y su estado por etapa."""

    key: str
    course_id: int
    course_name: str
    assignment_id: int
    assignment_name: str
    submitted_at: str = ""
    score: float | None = None
    points_possible: float | None = None
    is_group: bool = False
    stages: dict[str, StageResult] = field(default_factory=dict)

    def stage(self, stage: Stage) -> StageResult:
        return self.stages.setdefault(stage.value, StageResult())

    def set_stage(self, stage: Stage, status: StageStatus, reasons: list[str] | None = None) -> None:
        self.stages[stage.value] = StageResult(status, list(reasons or []))

    @property
    def grade_ratio(self) -> float | None:
        if self.score is None or not self.points_possible:
            return None
        return max(0.0, min(1.0, self.score / self.points_possible))

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "course_id": self.course_id,
            "course_name": self.course_name,
            "assignment_id": self.assignment_id,
            "assignment_name": self.assignment_name,
            "submitted_at": self.submitted_at,
            "score": self.score,
            "points_possible": self.points_possible,
            "is_group": self.is_group,
            "stages": {name: result.to_dict() for name, result in self.stages.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IndexEntry":
        return cls(
            key=data["key"],
            course_id=data["course_id"],
            course_name=data["course_name"],
            assignment_id=data["assignment_id"],
            assignment_name=data["assignment_name"],
            submitted_at=data.get("submitted_at", ""),
            score=data.get("score"),
            points_possible=data.get("points_possible"),
            is_group=data.get("is_group", False),
            stages={k: StageResult.from_dict(v) for k, v in data.get("stages", {}).items()},
        )

    @classmethod
    def from_submission(cls, sub: Submission) -> "IndexEntry":
        return cls(
            key=sub.key,
            course_id=sub.course.id,
            course_name=sub.course.name,
            assignment_id=sub.assignment_id,
            assignment_name=sub.assignment_name,
            submitted_at=sub.submitted_at,
            score=sub.score,
            points_possible=sub.points_possible,
            is_group=sub.is_group,
        )


@dataclass(frozen=True)
class UserInfo:
    id: int
    name: str
    email: str = ""
