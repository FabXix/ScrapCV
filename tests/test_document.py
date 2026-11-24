"""El CV se edita como documento y se guarda como Markdown: la conversión no debe perder nada."""
from scrapcv.analysis.posting import KeywordPostingAnalyzer
from scrapcv.ranking.ranker import SelectionCriteria
from scrapcv.writing.document import ContactItem, ResumeDocument, ResumeEducation, ResumeProject


def _doc():
    return ResumeDocument(
        name="Ana López", headline="Practicante de Marketing",
        contact=[ContactItem("ana@mail.com"), ContactItem("linkedin.com/in/ana", "https://linkedin.com/in/ana")],
        intro="Estudiante de Mercadotecnia con experiencia en campañas digitales.",
        competencies=[("Investigación de mercados", "Aplicada en dos proyectos.")],
        projects=[ResumeProject("Campaña para cafetería", "Proyecto en equipo · Mercadotecnia Digital · Mar 2026",
                                ["Diseñó una campaña en redes sociales.", "Analizó los resultados con Excel."],
                                "Herramientas", ["Excel", "Canva"], [("Video", "https://youtube.com/x")])],
        skills=[("Habilidades profesionales", ["Investigación de mercados", "Redacción"])],
        education=ResumeEducation("Licenciatura en Mercadotecnia", "ITESO", "2022 – 2026", ["Mercadotecnia Digital"]),
        order=["intro", "competencies", "projects", "skills", "education"],
        extra=[("Idiomas", "Inglés — intermedio (B1)")],
    )


def test_markdown_round_trip_keeps_everything():
    doc = _doc()
    again = ResumeDocument.from_markdown(doc.to_markdown())
    assert again == doc


def test_domains_become_links_and_empty_parts_disappear():
    doc = ResumeDocument(name="Ana", contact=[ContactItem("github.com/ana"), ContactItem("33 1234")],
                         projects=[ResumeProject("", bullets=["x"])], order=["projects"])
    markdown = doc.to_markdown()
    assert "[github.com/ana](https://github.com/ana)" in markdown and "33 1234" in markdown
    assert "## Proyectos" not in markdown  # un proyecto sin título no se publica


def test_generated_resume_can_be_edited_as_a_document(processed_app):
    result = processed_app.generate_for_posting("Practicante Backend\nRequisitos:\n- Python, SQL",
                                                SelectionCriteria(max_projects=2), "proyectos")
    doc = ResumeDocument.from_markdown(result.markdown)
    assert doc.name == "Estudiante Demo" and len(doc.projects) == 2 and doc.projects[0].bullets
    assert doc.to_markdown() == result.markdown


def test_non_technical_posting_works():
    posting = KeywordPostingAnalyzer().analyze(
        "Practicante de Recursos Humanos\nRequisitos:\n- Reclutamiento y selección de personal\n"
        "- Manejo de Excel\n- Estudiante de Psicología o afín\nDeseable:\n- Experiencia en capacitación\n")
    assert "Reclutamiento y selección de personal" in posting.required
    assert any("capacitación" in p.lower() for p in posting.preferred)
    assert not any("Psicología" in r for r in posting.required)  # es una condición, no una habilidad
