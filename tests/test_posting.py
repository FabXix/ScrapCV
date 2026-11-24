"""Flujo «vacante → CV a la medida» (principio de Resume Optimizer)."""
import io
import zipfile

from scrapcv.analysis.posting import FallbackPostingAnalyzer, KeywordPostingAnalyzer, LlmPostingAnalyzer
from scrapcv.domain.facts import Facts, LanguageStat
from scrapcv.domain.models import IndexEntry
from scrapcv.ports import LanguageModel
from scrapcv.ranking.ranker import ProjectCandidate, SelectionCriteria, WeightedRanker
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.export import DocxCvExporter, HtmlCvExporter, parse

POSTING = """Practicante Desarrollador Backend
Empresa: Acme Software
Responsabilidades:
- Desarrollar APIs REST con Python y Flask
Requisitos:
- Python, Git y SQL
- Inglés intermedio
Deseable:
- Docker, Java
- Trabajo en equipo
"""


class FakeModel(LanguageModel):
    def __init__(self, answer=None, fail=False):
        self._answer, self._fail = answer or {}, fail

    @property
    def name(self):
        return "falso"

    def is_available(self):
        return True

    def complete_json(self, system, prompt):
        if self._fail:
            raise RuntimeError("sin modelo")
        return self._answer


def test_keyword_analyzer_separates_required_and_preferred():
    posting = KeywordPostingAnalyzer().analyze(POSTING)
    assert posting.title == "Practicante Desarrollador Backend" and posting.company == "Acme Software"
    assert {"Python", "Git", "SQL", "Flask"} <= set(posting.required)
    assert set(posting.preferred) == {"Docker", "Java"}
    assert posting.soft_skills == ("Trabajo en equipo",)
    assert any("Inglés" in o for o in posting.other)


def test_llm_analyzer_drops_requirements_not_in_the_posting():
    model = FakeModel({"puesto": "Practicante Desarrollador Backend", "requisitos": ["Python", "Kubernetes"],
                       "deseables": ["Docker"]})
    posting = LlmPostingAnalyzer(model).analyze(POSTING)
    assert "Kubernetes" not in posting.required  # inventado por el modelo
    assert "Python" in posting.required and posting.source == "falso"


def test_posting_analyzer_falls_back_without_model():
    posting = FallbackPostingAnalyzer(LlmPostingAnalyzer(FakeModel(fail=True)), KeywordPostingAnalyzer()).analyze(POSTING)
    assert posting.source == "palabras clave" and "Python" in posting.required


def test_role_from_posting_matches_aliases():
    role = JobRole.from_posting(KeywordPostingAnalyzer().analyze("Requisitos: Node.js, MongoDB"))
    entry = IndexEntry("a", 1, "Web", 1, "API de contactos")
    facts = Facts("a", languages={"JavaScript": LanguageStat(3, 300)}, dependencies=["express", "mongoose", "mongodb"])
    ranked = WeightedRanker().rank([ProjectCandidate(entry, facts)], role)
    assert ranked[0].affinity == 1.0  # «mongodb» del package.json cubre «MongoDB»; node se infiere de express


def test_quizzes_and_empty_entries_are_not_projects():
    role = JobRole("Backend", frozenset({"python"}))
    code = Facts("x", languages={"Python": LanguageStat(1, 50)})
    quiz = ProjectCandidate(IndexEntry("q", 1, "BD", 1, "Quiz Sesiones 2 y 3 - API REST"), code)
    empty = ProjectCandidate(IndexEntry("e", 1, "BD", 2, "Proyecto Python"), Facts("e"))
    real = ProjectCandidate(IndexEntry("r", 1, "BD", 3, "Cliente en Python"), code)
    selected = WeightedRanker().select([quiz, empty, real], role, SelectionCriteria())
    assert [r.candidate.entry.key for r in selected] == ["r"]


def test_full_flow_reports_match_gaps_and_tips(processed_app):
    result = processed_app.generate_for_posting(POSTING, SelectionCriteria(max_projects=3), "proyectos")
    report = result.report
    assert 0 < report.percentage < 100
    met = {r.name for r in report.strengths}
    gaps = {r.name for r in report.gaps}
    assert "Python" in met and "Java" in met
    assert "Docker" in gaps
    assert report.tips  # sugerencias accionables
    assert result.markdown.startswith("# Estudiante Demo") and "**Practicante Desarrollador Backend**" in result.markdown
    assert "Reporte de laboratorio escaneado" not in result.markdown  # sin contenido legible
    assert any("Inglés" in note for note in result.review)
    evidence = result.path.with_name(result.path.stem + ".evidencia.json")
    assert evidence.exists()


def test_exports_html_and_docx(processed_app):
    result = processed_app.generate_for_posting(POSTING, SelectionCriteria(max_projects=2), "proyectos")
    html_path = processed_app.export_cv(result.role, result.markdown, "proyectos", "html")
    page = html_path.read_text("utf-8")
    assert "<h1>Estudiante Demo</h1>" in page and 'class="headline"' in page and "window.print()" in page
    docx_path = processed_app.export_cv(result.role, result.markdown, "proyectos", "docx")
    with zipfile.ZipFile(docx_path) as docx:
        xml = docx.read("word/document.xml").decode("utf-8")
    assert "Estudiante Demo" in xml and "PROYECTOS" in xml


def test_exporters_ignore_internal_markup_and_unsafe_links():
    markdown = "# Ana\n\n- Hizo algo <!-- evidencia: raw/x --> <sub>Evidencia: x</sub>\n- [clic](javascript:alert(1))\n"
    assert parse(markdown)[1].items[0] == "Hizo algo"
    page = HtmlCvExporter().export(markdown).decode()
    assert "javascript:" not in page and "evidencia" not in page.lower()
    assert zipfile.is_zipfile(io.BytesIO(DocxCvExporter().export(markdown)))


def test_same_repository_is_one_project_and_proves_git():
    from scrapcv.domain.facts import LinkRef

    role = JobRole.from_posting(KeywordPostingAnalyzer().analyze("Requisitos: Express, Git"))
    def candidate(key, name):
        facts = Facts(key, languages={"JavaScript": LanguageStat(3, 300)}, dependencies=["express"],
                      links=[LinkRef("https://github.com/a/app.git", "repositorio")])
        return ProjectCandidate(IndexEntry(key, 1, "Web", 1, name), facts)
    selected = WeightedRanker().select([candidate("a", "Backend"), candidate("b", "Entrega final")], role, SelectionCriteria())
    assert len(selected) == 1 and selected[0].affinity == 1.0
