"""Prompts del currículum: uno por sección redactada, más el contexto que recibe el modelo.

Aquí solo vive el texto que se le manda al modelo; quién lo llama y qué pasa
si falla está en `writers.py`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from scrapcv.domain.posting import JobPosting
from scrapcv.writing.format import clean_title, pretty_course

if TYPE_CHECKING:
    from scrapcv.ranking.ranker import RankedProject

_COMMON_RULES = (
    "Reglas estrictas:\n"
    "- Usa SOLO la información proporcionada. No inventes empresas, cargos, herramientas, usuarios ni logros.\n"
    "- NO escribas números, cifras, porcentajes ni métricas de ningún tipo.\n"
    "- Español profesional, sin «yo», sin adjetivos vacíos (apasionado, proactivo, excelente).\n"
    "- Si hay vacante, usa su vocabulario SOLO para describir lo que sí aparece en la evidencia.\n"
)

SUMMARY_SYSTEM = (
    "Eres un redactor de currículums para estudiantes universitarios de cualquier carrera.\n" + _COMMON_RULES +
    "- {focus}\n"
    "- Menciona primero las habilidades o herramientas que pide la vacante y que el estudiante sí demostró.\n"
    "- No describas tareas escolares («entregó», «materia», «tarea»): habla de lo que construyó.\n"
    'Responde únicamente un objeto JSON: {{"texto": str}}'
)

PROJECT_SYSTEM = (
    "Eres un redactor de currículums. Conviertes un proyecto académico en una entrada de CV.\n" + _COMMON_RULES +
    "- «titulo»: nombre del proyecto como producto, máximo seis palabras, sin «tarea», «lab» ni «proyecto final».\n"
    "- «vinetas»: exactamente {count}. Cada una es UNA frase de máximo veinte palabras que empieza con un verbo en "
    "pasado (Desarrolló, Diseñó, Implementó, Modeló, Automatizó).\n"
    "- Fórmula de cada viñeta: qué hizo o creó + con qué método o herramienta + para qué sirve o qué resolvió.\n"
    "- Si el proyecto no es de software (un análisis, un reporte, una campaña, un diseño), descríbelo con verbos "
    "como Analizó, Elaboró, Propuso, Investigó, Presentó.\n"
    "- Si el proyecto fue en equipo usa «Colaboró en» o «Participó en» en al menos una viñeta.\n"
    "- Prohibido: «entregó», «la tarea», «la materia», «el profesor», cantidades de líneas o archivos.\n"
    "Ejemplo de estilo (no copies su contenido):\n"
    '{{"titulo": "API de gestión de contactos", "vinetas": ["Desarrolló una API REST con Node.js y Express para '
    'administrar contactos con autenticación JWT.", "Modeló la persistencia en MongoDB con validación de datos."]}}\n'
    '{{"titulo": "Plan de negocio para una cafetería", "vinetas": ["Analizó el mercado local y la competencia para '
    'definir el público objetivo.", "Propuso una estrategia de precios y un plan de lanzamiento en equipo."]}}\n'
    'Responde únicamente un objeto JSON: {{"titulo": str, "vinetas": [str]}}'
)

COMPETENCIES_SYSTEM = (
    "Eres un redactor de currículums. Agrupas lo que el estudiante demostró en sus proyectos en "
    "tres a cinco competencias clave para el puesto.\n" + _COMMON_RULES +
    "- «titulo»: dos a cuatro palabras. «descripcion»: una frase de máximo veinte palabras que cite lo hecho en los proyectos.\n"
    'Responde únicamente un objeto JSON: {"competencias": [{"titulo": str, "descripcion": str}]}'
)

TIPS_SYSTEM = (
    "Eres un asesor de carrera que revisa el CV de un estudiante contra una vacante.\n"
    "- Da exactamente tres consejos concretos para mejorar el CV o la candidatura.\n"
    "- Cada consejo: una o dos frases, accionable, en segunda persona («Agrega…», «Destaca…»).\n"
    "- Basa los consejos en los requisitos cubiertos y faltantes que recibes; no inventes experiencia.\n"
    "- No escribas porcentajes ni cifras.\n"
    'Responde únicamente un objeto JSON: {"consejos": [str]}'
)


def posting_context(posting: JobPosting | None) -> str:
    if posting is None:
        return ""
    lines = [f"Vacante: {posting.title}" + (f" en {posting.company}" if posting.company else "")]
    if posting.required:
        lines.append("Requisitos: " + ", ".join(posting.required))
    if posting.preferred:
        lines.append("Deseables: " + ", ".join(posting.preferred))
    if posting.responsibilities:
        lines.append("Responsabilidades: " + "; ".join(posting.responsibilities[:4]))
    return "\n".join(lines)


def project_context(ranked: "RankedProject") -> str:
    entry, facts, profile = ranked.candidate.entry, ranked.candidate.facts, ranked.candidate.profile
    parts = [f"- Proyecto «{clean_title(entry.assignment_name)}» (materia: {pretty_course(entry.course_name)})"
             + (" [PROYECTO EN EQUIPO]" if entry.is_group else "")]
    if profile:
        if profile.summary and profile.origin != "estatico":
            parts.append(f"  Qué hace: {profile.summary}")
        if profile.technologies:
            parts.append(f"  Tecnologías: {', '.join(profile.technologies)}")
        if profile.skills:
            parts.append(f"  Habilidades aplicadas: {', '.join(profile.skills)}")
        if profile.scope and profile.origin != "estatico":
            parts.append(f"  Alcance: {profile.scope}")
    skills = [s.name for s in ranked.candidate.skills()]
    if skills:
        parts.append(f"  Tecnologías detectadas en el código: {', '.join(skills)}")
    docs = sorted({d.kind for d in facts.documents})
    if docs:
        parts.append(f"  Documentos: {', '.join(docs)}")
    if any(link.kind == "repositorio" for link in facts.links):
        parts.append("  Tiene repositorio público.")
    return "\n".join(parts)
