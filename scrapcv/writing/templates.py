"""Plantillas de currículum: qué secciones lleva y en qué orden."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResumeTemplate:
    key: str
    name: str
    description: str
    sections: tuple[str, ...]
    intro_focus: str = ""  # instrucción para el prompt del perfil / objetivo
    bullets_per_project: int = 3
    default_projects: int = 3


PROJECT_BASED = ResumeTemplate(
    key="proyectos",
    name="Por proyectos (recomendado)",
    description="Perfil breve, proyectos destacados con logros, habilidades por categoría y educación. "
                "El formato más común para estudiantes de software.",
    sections=("header", "summary", "projects", "skills", "education"),
    intro_focus=(
        "Escribe 2 o 3 frases: quién es (estudiante orientado al puesto), qué tecnologías domina según sus "
        "proyectos y qué tipo de soluciones ha construido."
    ),
    bullets_per_project=3,
    default_projects=3,
)
SKILLS_BASED = ResumeTemplate(
    key="funcional",
    name="Por competencias (funcional)",
    description="Primero las competencias clave, cada una respaldada por proyectos. Útil si aún no tienes experiencia laboral.",
    sections=("header", "summary", "competencies", "skills", "projects", "education"),
    intro_focus="Escribe 2 frases: perfil del estudiante para el puesto y en qué se especializa.",
    bullets_per_project=2,
    default_projects=4,
)
INTERNSHIP = ResumeTemplate(
    key="practicas",
    name="Prácticas profesionales",
    description="Objetivo profesional y educación arriba, proyectos en breve. Para solicitar prácticas o primer empleo.",
    sections=("header", "objective", "education", "projects", "skills"),
    intro_focus=(
        "Escribe 2 frases como objetivo profesional: qué puesto de prácticas busca, qué puede aportar con lo "
        "que ya construyó y en qué quiere crecer."
    ),
    bullets_per_project=2,
    default_projects=3,
)
HYBRID = ResumeTemplate(
    key="hibrido",
    name="Híbrido (habilidades primero)",
    description="Perfil y habilidades arriba para que el reclutador vea el stack en segundos; luego proyectos.",
    sections=("header", "summary", "skills", "projects", "education"),
    intro_focus="Escribe 2 frases: perfil del estudiante para el puesto y sus principales tecnologías.",
    bullets_per_project=2,
    default_projects=4,
)
TEMPLATES: tuple[ResumeTemplate, ...] = (PROJECT_BASED, SKILLS_BASED, INTERNSHIP, HYBRID)


def template_by_key(key: str) -> ResumeTemplate | None:
    return next((t for t in TEMPLATES if t.key == key), None)
