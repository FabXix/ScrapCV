"""Adaptador de la API REST de Canvas a las entidades del dominio (patrón Adapter).

Solo usa la API oficial; no hay scraping de HTML (sección 6.1).
"""
from __future__ import annotations

from pathlib import Path

from scrapcv.domain.models import Attachment, Comment, Course, Submission, UserInfo
from scrapcv.infrastructure.canvas.http_client import CanvasHttpClient
from scrapcv.ports import AttachmentDownloader, CanvasReader


class CanvasApiGateway(CanvasReader, AttachmentDownloader):
    def __init__(self, client: CanvasHttpClient) -> None:
        self._client = client

    def current_user(self) -> UserInfo:
        data = self._client.get_json("users/self")
        return UserInfo(id=data["id"], name=data.get("name", ""), email=data.get("primary_email", "") or "")

    def list_courses(self) -> list[Course]:
        courses: dict[int, Course] = {}
        for state in ("active", "completed"):  # CAR-02: activas y completadas
            params = [("enrollment_state", state), ("include[]", "term"), ("per_page", "100")]
            for raw in self._client.get_paginated("courses", params):
                if "id" not in raw or raw.get("access_restricted_by_date"):
                    continue
                courses[raw["id"]] = Course(
                    id=raw["id"],
                    name=raw.get("name", f"Materia {raw['id']}"),
                    code=raw.get("course_code", ""),
                    term=(raw.get("term") or {}).get("name", ""),
                    state=state,
                )
        return list(courses.values())

    def list_submissions(self, course: Course) -> list[Submission]:
        params = [
            ("student_ids[]", "self"),
            ("include[]", "assignment"),
            ("include[]", "submission_comments"),
            ("include[]", "group"),
            ("per_page", "100"),
        ]
        path = f"courses/{course.id}/students/submissions"
        return [self._to_submission(course, raw) for raw in self._client.get_paginated(path, params)]

    def download(self, url: str, destination: Path) -> None:
        self._client.download(url, destination)

    # --- Mapeo -----------------------------------------------------------------
    @staticmethod
    def _to_submission(course: Course, raw: dict) -> Submission:
        assignment = raw.get("assignment") or {}
        group = raw.get("group") or {}
        attachments = tuple(
            Attachment(
                id=a.get("id", 0),
                filename=a.get("display_name") or a.get("filename") or f"adjunto_{a.get('id')}",
                url=a.get("url", ""),
                size=a.get("size", 0) or 0,
                content_type=a.get("content-type", ""),
            )
            for a in raw.get("attachments") or []
        )
        comments = tuple(
            Comment(author=c.get("author_name", ""), text=c.get("comment", ""), created_at=c.get("created_at", ""))
            for c in raw.get("submission_comments") or []
        )
        return Submission(
            id=raw.get("id", 0),
            course=course,
            assignment_id=raw.get("assignment_id", assignment.get("id", 0)),
            assignment_name=assignment.get("name", f"Tarea {raw.get('assignment_id')}"),
            submitted_at=raw.get("submitted_at") or "",
            score=raw.get("score"),
            grade=raw.get("grade"),
            points_possible=assignment.get("points_possible"),
            submission_type=raw.get("submission_type") or "",
            body=raw.get("body") or "",
            url=raw.get("url") or "",
            attachments=attachments,
            comments=comments,
            is_group=bool(group.get("id") or assignment.get("group_category_id")),
        )
