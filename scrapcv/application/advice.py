"""Análisis del CV contra la vacante: match, fortalezas, brechas y sugerencias.

Es el equivalente a las salidas «Match Percentage», «Strengths and Weaknesses» e
«Improvement Tips» de Resume Optimizer, pero con el porcentaje calculado sobre la
evidencia real y no estimado por el modelo.
"""
from __future__ import annotations

from scrapcv.ranking.match import MatchAnalyzer, MatchReport
from scrapcv.ranking.ranker import ProjectCandidate
from scrapcv.writing.writers import WriterChain, WritingRequest


class CvAdvisor:
    def __init__(self, matcher: MatchAnalyzer, writers: WriterChain) -> None:
        self._matcher = matcher
        self._writers = writers

    def advise(self, request: WritingRequest, candidates: list[ProjectCandidate]) -> MatchReport | None:
        posting = request.role.posting
        if posting is None:
            return None
        report = self._matcher.analyze(posting, request.ranked, candidates)
        tips, _note = self._writers.write("Sugerencias", lambda w: w.tips(request, report))
        report.tips = list(tips or [])
        return report
