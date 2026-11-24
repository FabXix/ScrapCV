import re

import pytest

from scrapcv.domain.facts import DocumentStat, Facts, LanguageStat, LinkRef, ProjectProfile
from scrapcv.domain.models import ContactInfo, IndexEntry, UserInfo
from scrapcv.ports import LanguageModel
from scrapcv.ranking.ranker import ProjectCandidate, WeightedRanker
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.format import clean_title, month_year, pretty_course, pretty_name
from scrapcv.writing.resume import TEMPLATES, ResumeBuilder, template_by_key
from scrapcv.writing.writers import LlmResumeWriter, RuleBasedResumeWriter, WriterChain

ROLE = JobRole("Desarrollador Backend", frozenset({"python", "flask", "api"}))
CONTACT = ContactInfo(phone="33 1234 5678", location="Guadalajara", linkedin="linkedin.com/in/ana",
                      github="github.com/ana", degree="Ingeniería en Sistemas", institution="ITESO", period="2022 – 2026")


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
        if "entrada de CV" in system:
            return {"titulo": "API de tareas", "vinetas": ["Desarrolló una API REST con 15 endpoints.",
                                                           "Implementó autenticación con Flask."]}
        if "competencias" in system:
            return {"competencias": [{"titulo": "Desarrollo de APIs", "descripcion": "Construyó servicios web."}]}
        return {"texto": "Estudiante enfocado en backend con 4 proyectos."}


def _ranked(group=True, name="Tarea 4: API de tareas"):
    entry = IndexEntry("m_1/t_1", 1, "PROGRAMACION WEB (O2025_ESI3124N)", 1, name, "2025-12-06T10:00:00Z",
                       score=9, points_possible=10, is_group=group)
    facts = Facts("m_1/t_1", languages={"Python": LanguageStat(2, 120)}, dependencies=["flask", "python-dotenv"],
                  documents=[DocumentStat("reporte.pdf", "pdf", 900, 4)], links=[LinkRef("https://github.com/a/b", "repositorio")],
                  code_files=["app.py"], dependency_files=["requirements.txt"], evidence_files=["app.py"])
    profile = ProjectProfile("m_1/t_1", "Construyó una API REST.", ["Flask"], ["APIs"], sources=["README.md"], origin="falso")
    return WeightedRanker().rank([ProjectCandidate(entry, facts, profile)], ROLE)


def _chain(model=None):
    return WriterChain(([LlmResumeWriter(model)] if model else []) + [RuleBasedResumeWriter()])


def _build(template_key, model=None, contact=CONTACT):
    builder = ResumeBuilder(_chain(model))
    return builder.build(UserInfo(1, "ANA LÓPEZ", "ana@mail.com"), contact, ROLE, template_by_key(template_key), _ranked())


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.key)
def test_every_template_renders_a_clean_resume(template):
    draft = _build(template.key, FakeModel())
    headings = re.findall(r"^## (.+)$", draft.markdown, re.M)
    assert draft.markdown.startswith("# Ana López")
    assert "[linkedin.com/in/ana](https://linkedin.com/in/ana)" in draft.markdown
    assert "Habilidades" in headings and "Educación" in headings
    # Nada de notas internas, rutas ni comentarios dentro del CV
    assert "Verificar" not in draft.markdown and "<!--" not in draft.markdown and "raw/" not in draft.markdown


def test_project_based_order():
    headings = re.findall(r"^## (.+)$", _build("proyectos", FakeModel()).markdown, re.M)
    assert headings == ["Perfil profesional", "Proyectos", "Habilidades", "Educación"]


def test_internship_starts_with_objective_and_education():
    headings = re.findall(r"^## (.+)$", _build("practicas", FakeModel()).markdown, re.M)
    assert headings[:2] == ["Objetivo profesional", "Educación"]


def test_project_looks_like_a_cv_entry():
    markdown = _build("proyectos", FakeModel()).markdown
    assert "### API de tareas  ·  [Repositorio](https://github.com/a/b)" in markdown
    assert "*Proyecto en equipo · Programación Web · Dic 2025*" in markdown
    assert "O2025_ESI3124N" not in markdown and "Tarea 4" not in markdown
    assert "líneas" not in markdown  # contar líneas de código no es un logro
    assert "dotenv" not in markdown  # dependencias sin valor para un reclutador


def test_model_numbers_are_stripped():
    markdown = _build("proyectos", FakeModel()).markdown
    assert "15" not in markdown and "4 proyectos" not in markdown


def test_works_without_model_and_asks_for_review():
    draft = _build("proyectos", None)
    assert "Ingeniería en Sistemas con experiencia práctica en Python" in draft.markdown
    assert any("sin modelo" in note for note in draft.review)
    assert "Construyó una API REST." in draft.markdown  # viñeta tomada del perfil


def test_model_failure_falls_back_to_rules():
    draft = _build("funcional", FakeModel(fail=True))
    assert "## Competencias clave" in draft.markdown and "Desarrollo backend" in draft.markdown
    assert any("Competencias clave" in note for note in draft.review)


def test_each_ai_section_has_its_own_prompt():
    model = FakeModel()
    _build("proyectos", model)
    assert len(set(model.systems)) == 2  # perfil y proyecto


def test_skills_are_grouped_by_category_and_soft_skills_need_evidence():
    markdown = _build("proyectos", FakeModel()).markdown
    assert "- **Lenguajes:** Python" in markdown
    assert "- **Frameworks y librerías:** Flask" in markdown
    assert "- **Competencias:** Trabajo en equipo, Documentación técnica" in markdown
    ranked = _ranked(group=False)
    ranked[0].candidate.facts.documents.clear()
    solo = ResumeBuilder(_chain()).build(UserInfo(1, "Ana"), CONTACT, ROLE, template_by_key("proyectos"), ranked)
    assert "Competencias:" not in solo.markdown


def test_missing_data_goes_to_review_not_into_the_cv():
    draft = _build("proyectos", None, ContactInfo())
    assert any("LinkedIn, GitHub, teléfono" in note for note in draft.review)
    assert any("Educación" in note for note in draft.review)
    assert "[Carrera]" in draft.markdown  # marcador visible para completar


def test_evidence_is_kept_outside_the_cv():
    draft = _build("proyectos", FakeModel())
    assert draft.evidence and draft.evidence[0]["evidencia"][0].startswith("raw/m_1/t_1/")


@pytest.mark.parametrize("raw, expected", [
    ("Proyecto final: Sistema de inventario", "Sistema de inventario"),
    ("MongoDB Lab 2 - MongoDB con Acciones de una REST API", "MongoDB con Acciones de una REST API"),
    ("Práctica: Banco concurrente", "Banco concurrente"),
    ("Backend Completo - REST API", "Backend Completo — REST API"),
])
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


def test_text_formatting():
    assert pretty_course("BASES DE DATOS NO RELACIONALES (P2026_ESI3891B)") == "Bases de Datos No Relacionales"
    assert pretty_course("Programación Orientada a Objetos") == "Programación Orientada a Objetos"
    assert pretty_name("MARIA DE LA CRUZ") == "Maria de la Cruz"
    assert month_year("2026-03-10T00:00:00Z") == "Mar 2026" and month_year("") == ""
