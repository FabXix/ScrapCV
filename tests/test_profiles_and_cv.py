import re

from scrapcv.analysis.profilers import FallbackProjectProfiler, LlmProjectProfiler, StaticProjectProfiler
from scrapcv.domain.facts import Facts, LanguageStat, TextSnippet
from scrapcv.domain.models import IndexEntry, UserInfo
from scrapcv.ports import LanguageModel
from scrapcv.ranking.ranker import ProjectCandidate, SelectionCriteria, WeightedRanker
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.cv import CvComposer, MarkdownCvRenderer, untraceable_bullets


class FakeModel(LanguageModel):
    def __init__(self, answer=None, fail=False):
        self._answer = answer or {}
        self._fail = fail
        self.prompts = []

    @property
    def name(self):
        return "falso"

    def is_available(self):
        return True

    def complete_json(self, system, prompt):
        self.prompts.append(prompt)
        if self._fail:
            raise RuntimeError("sin modelo")
        return self._answer


def _entry(group=False):
    return IndexEntry("m_1/t_1", 1, "Materia", 1, "Tarea", score=9, points_possible=10, is_group=group)


def _facts():
    return Facts("m_1/t_1", languages={"Python": LanguageStat(2, 120)}, dependencies=["flask"],
                 code_files=["app.py"], dependency_files=["requirements.txt"], evidence_files=["app.py"])


SNIPPETS = [TextSnippet("README.md", "API REST hecha con Flask", 1)]


def test_llm_numbers_are_removed_and_flagged():
    model = FakeModel({"resumen": "Desarrolló una API con 15 endpoints y 95% de cobertura.",
                       "tecnologias": ["Flask", "Kubernetes"], "habilidades": [], "dudoso": []})
    profile = LlmProjectProfiler(model).profile(_entry(), _facts(), SNIPPETS)
    assert not re.search(r"\d", profile.summary)
    assert profile.technologies == ["Flask"]  # Kubernetes no está en la evidencia
    assert any("Kubernetes" in d for d in profile.doubtful)
    assert any("cifras" in d for d in profile.doubtful)


def test_group_project_is_marked():
    profile = LlmProjectProfiler(FakeModel({"resumen": "Hizo una API."})).profile(_entry(group=True), _facts(), SNIPPETS)
    assert profile.role.startswith("Proyecto en equipo")


def test_context_is_bounded():
    model = FakeModel({"resumen": "ok"})
    huge = [TextSnippet(f"f{i}.py", "x" * 5000, 5) for i in range(20)]
    LlmProjectProfiler(model).profile(_entry(), _facts(), huge)
    assert len(model.prompts[0]) < 8000


def test_fallback_when_model_fails():
    profiler = FallbackProjectProfiler(LlmProjectProfiler(FakeModel(fail=True)), StaticProjectProfiler())
    profile = profiler.profile(_entry(), _facts(), SNIPPETS)
    assert profile.origin == "estatico"
    assert "no respondió" in profile.doubtful[0]


def test_cv_numbers_come_only_from_facts():
    model = FakeModel({"resumen": "Construyó un servicio web.", "tecnologias": ["Flask"]})
    profile = LlmProjectProfiler(model).profile(_entry(), _facts(), SNIPPETS)
    candidate = ProjectCandidate(_entry(), _facts(), profile)
    role = JobRole("Backend", frozenset({"python", "flask"}))
    ranked = WeightedRanker().rank([candidate], role)
    document = CvComposer().compose(UserInfo(1, "Ana"), role, ranked)
    assert untraceable_bullets(document) == []
    markdown = MarkdownCvRenderer().render(document)
    body = markdown.split("## Proyectos académicos")[1]
    numbers = set(re.findall(r"(?<![\w-])\d+(?:\.\d+)?(?![\w-])", re.sub(r"<sub>.*?</sub>", "", body)))
    allowed = {"120", "2", "9", "10", "1"}  # facts.json y la calificación de Canvas
    assert numbers <= allowed, numbers


def test_filters_include_exclude_and_max():
    a = ProjectCandidate(IndexEntry("a", 1, "Redes", 1, "A"), _facts())
    b = ProjectCandidate(IndexEntry("b", 2, "Datos", 2, "B"), _facts())
    role = JobRole("Backend", frozenset({"python"}))
    ranker = WeightedRanker()
    assert [r.candidate.entry.key for r in ranker.select([a, b], role, SelectionCriteria(include_courses=frozenset({"Datos"})))] == ["b"]
    assert [r.candidate.entry.key for r in ranker.select([a, b], role, SelectionCriteria(exclude_courses=frozenset({"Datos"})))] == ["a"]
    assert len(ranker.select([a, b], role, SelectionCriteria(max_projects=1))) == 1


def test_custom_role_keywords():
    role = JobRole.custom("Mi puesto", "python, machine learning, sql")
    assert role.keywords == frozenset({"python", "machine learning", "sql"})
