import re

import pytest

from scrapcv.domain.facts import DocumentStat, Facts, LanguageStat, LinkRef, ProjectProfile
from scrapcv.domain.models import ContactInfo, IndexEntry, UserInfo
from scrapcv.ports import LanguageModel
from scrapcv.ranking.ranker import ProjectCandidate, WeightedRanker
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.resume import TEMPLATES, ResumeBuilder, ResumeWriter, template_by_key

ROLE = JobRole("Desarrollador Backend", frozenset({"python", "flask", "api"}))
CONTACT = ContactInfo(phone="33 1234 5678", location="Guadalajara", linkedin="linkedin.com/in/ana", github="github.com/ana")


class FakeModel(LanguageModel):
    def __init__(self, fail=False):
        self.fail, self.systems = fail, []

    @property
    def name(self):
        return "falso"

    def is_available(self):
        return True

    def complete_json(self, system, prompt):
        self.systems.append(system)
        if self.fail:
            raise RuntimeError("sin modelo")
        if "habilidades blandas" in system:
            return {"habilidades": [{"id": "trabajo_en_equipo", "frase": "Coordinó entregas con 3 compañeros."},
                                    {"id": "liderazgo", "frase": "Inventada."}]}
        if "viñetas" in system:
            return {"vinetas": ["Desarrolló una API REST con 15 endpoints.", "Implementó autenticación con Flask."]}
        if "competencias" in system:
            return {"competencias": [{"titulo": "Desarrollo de APIs", "descripcion": "Construyó servicios web."}]}
        return {"texto": "Estudiante enfocado en backend con 4 proyectos."}


def _ranked(group=True):
    entry = IndexEntry("m_1/t_1", 1, "Programación Web", 1, "API de tareas", score=9, points_possible=10, is_group=group)
    facts = Facts("m_1/t_1", languages={"Python": LanguageStat(2, 120)}, dependencies=["flask"],
                  documents=[DocumentStat("reporte.pdf", "pdf", 900, 4)], links=[LinkRef("https://github.com/a/b", "repositorio")],
                  code_files=["app.py"], dependency_files=["requirements.txt"], evidence_files=["app.py"])
    profile = ProjectProfile("m_1/t_1", "Construyó una API REST.", ["Flask"], ["APIs"], sources=["README.md"])
    return WeightedRanker().rank([ProjectCandidate(entry, facts, profile)], ROLE)


def _build(template_key, model=None):
    builder = ResumeBuilder(ResumeWriter(model))
    return builder.build(UserInfo(1, "Ana López", "ana@mail.com"), CONTACT, ROLE, template_by_key(template_key), _ranked())


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.key)
def test_every_template_renders_its_sections_in_order(template):
    markdown = _build(template.key, FakeModel())
    headings = re.findall(r"^## (.+)$", markdown, re.M)
    assert headings and markdown.startswith("# Ana López")
    assert "[LinkedIn](https://linkedin.com/in/ana)" in markdown and "[GitHub](https://github.com/ana)" in markdown
    assert "Habilidades técnicas" in headings and "Formación académica" in headings


def test_project_based_order():
    headings = re.findall(r"^## (.+)$", _build("proyectos", FakeModel()), re.M)
    assert headings == ["Resumen profesional", "Proyectos", "Habilidades técnicas", "Habilidades blandas", "Formación académica"]


def test_internship_starts_with_objective_and_education():
    headings = re.findall(r"^## (.+)$", _build("practicas", FakeModel()), re.M)
    assert headings[:2] == ["Objetivo profesional", "Formación académica"]


def test_model_numbers_are_stripped_and_unknown_soft_skills_dropped():
    markdown = _build("proyectos", FakeModel())
    prose = re.sub(r"<!--.*?-->", "", markdown)
    assert "15" not in prose and "4 proyectos" not in prose and "3 compañeros" not in prose
    assert "Liderazgo" not in markdown and "Inventada" not in markdown
    assert "**Trabajo en equipo:**" in markdown


def test_works_without_model_and_flags_generated_text():
    markdown = _build("proyectos", None)
    assert "Estudiante orientado a Desarrollador Backend" in markdown
    assert "Redactado sin modelo" in markdown
    assert "Construyó una API REST." in markdown  # viñeta tomada del perfil


def test_model_failure_falls_back():
    markdown = _build("funcional", FakeModel(fail=True))
    assert "## Competencias clave" in markdown and "Competencias sin modelo" in markdown


def test_each_ai_section_has_its_own_prompt():
    model = FakeModel()
    _build("proyectos", model)
    assert len(set(model.systems)) == 3  # resumen, viñetas y habilidades blandas


def test_soft_skills_require_evidence():
    ranked = _ranked(group=False)
    ranked[0].candidate.facts.documents.clear()
    ranked[0].candidate.facts.links.clear()
    markdown = ResumeBuilder(ResumeWriter(None)).build(UserInfo(1, "Ana"), CONTACT, ROLE, template_by_key("proyectos"), ranked)
    assert "Habilidades blandas" not in markdown


def test_missing_contact_is_flagged_and_evidence_is_hidden_in_comments():
    markdown = ResumeBuilder(ResumeWriter(None)).build(
        UserInfo(1, "Ana"), ContactInfo(), ROLE, template_by_key("proyectos"), _ranked())
    assert "Verificar:** agrega LinkedIn, GitHub, teléfono" in markdown
    assert "<!-- evidencia: raw/m_1/t_1" in markdown
    assert "<sub>" not in markdown


def test_numbers_in_resume_only_come_from_facts():
    prose = re.sub(r"<!--.*?-->", "", _build("proyectos", FakeModel()))
    body = prose.split("## Proyectos")[1].split("## Habilidades blandas")[0]
    assert set(re.findall(r"(?<![\w-])\d+(?![\w-])", body)) <= {"120", "2", "1"}
