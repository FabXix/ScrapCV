"""Generador de currículum por plantillas (Markdown).

Una plantilla (`ResumeTemplate`) decide QUÉ secciones lleva el currículum y en
qué orden. Cada sección redactada por IA tiene su propio prompt y una versión
sin modelo, así el currículum siempre se puede generar aunque Ollama no esté.

Reglas de veracidad (las mismas que el resto de ScrapCV):
- Las cifras salen solo de `Facts`; el texto del modelo pasa por `strip_numbers`.
- Las habilidades blandas solo se aceptan si hay una señal en la evidencia.
- Cada bloque guarda su evidencia en un comentario HTML (invisible al exportar).
- Lo que el modelo no pudo respaldar se marca con «Verificar» para que el usuario lo revise.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from scrapcv.analysis.guards import strip_numbers
from scrapcv.domain.models import ContactInfo, UserInfo
from scrapcv.ports import LanguageModel
from scrapcv.ranking.ranker import RankedProject
from scrapcv.ranking.roles import JobRole
from scrapcv.writing.cv import FactsPhraser

log = logging.getLogger("scrapcv.resume")

# --- Plantillas -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumeTemplate:
    key: str
    name: str
    description: str
    sections: tuple[str, ...]
    intro_focus: str = ""  # instrucción para el prompt del resumen / objetivo
    bullets_per_project: int = 3
    default_projects: int = 3


PROJECT_BASED = ResumeTemplate(
    key="proyectos",
    name="Por proyectos (recomendado)",
    description="Encabezado con LinkedIn/GitHub, resumen breve, proyectos destacados, habilidades técnicas y blandas.",
    sections=("header", "summary", "projects", "hard_skills", "soft_skills", "education"),
    intro_focus=(
        "Escribe 2 o 3 frases: quién es (estudiante orientado al puesto), qué tecnologías usó en sus proyectos "
        "y qué tipo de proyectos ha construido."
    ),
    bullets_per_project=3,
    default_projects=3,
)
SKILLS_BASED = ResumeTemplate(
    key="funcional",
    name="Por competencias (funcional)",
    description="Primero las competencias clave, cada una respaldada por proyectos. Útil si aún no tienes experiencia laboral.",
    sections=("header", "competencies", "hard_skills", "projects", "soft_skills", "education"),
    bullets_per_project=1,
    default_projects=4,
)
INTERNSHIP = ResumeTemplate(
    key="practicas",
    name="Prácticas profesionales",
    description="Objetivo profesional y formación al inicio, proyectos en breve. Para solicitar prácticas o primer empleo.",
    sections=("header", "objective", "education", "projects", "hard_skills", "soft_skills"),
    intro_focus=(
        "Escribe 1 o 2 frases como objetivo profesional: que busca realizar prácticas profesionales en el puesto, "
        "qué puede aportar con lo que ya construyó y su disposición para aprender."
    ),
    bullets_per_project=2,
    default_projects=3,
)
HYBRID = ResumeTemplate(
    key="hibrido",
    name="Híbrido",
    description="Resumen y habilidades clave arriba, luego proyectos y habilidades blandas.",
    sections=("header", "summary", "hard_skills", "projects", "soft_skills", "education"),
    intro_focus="Escribe 2 frases: perfil del estudiante para el puesto y sus principales tecnologías.",
    bullets_per_project=2,
    default_projects=4,
)
TEMPLATES: tuple[ResumeTemplate, ...] = (PROJECT_BASED, SKILLS_BASED, INTERNSHIP, HYBRID)


def template_by_key(key: str) -> ResumeTemplate | None:
    return next((t for t in TEMPLATES if t.key == key), None)


# --- Prompts (uno por sección redactada) -----------------------------------------------------------

_COMMON_RULES = (
    "Reglas estrictas:\n"
    "- Usa SOLO la información proporcionada. No inventes empresas, cargos, títulos, herramientas ni logros.\n"
    "- NO escribas números, cifras, porcentajes ni métricas de ningún tipo.\n"
    "- Escribe en español, tono profesional, sin usar «yo».\n"
)

INTRO_SYSTEM = (
    "Eres un redactor de currículums para estudiantes universitarios.\n" + _COMMON_RULES +
    "- {focus}\n"
    'Responde únicamente un objeto JSON: {{"texto": str}}'
)

BULLETS_SYSTEM = (
    "Eres un redactor de currículums. Conviertes un proyecto académico en viñetas de logro.\n" + _COMMON_RULES +
    "- Cada viñeta es una sola frase de máximo 22 palabras y empieza con un verbo en pasado (Desarrolló, Diseñó, Implementó).\n"
    "- Primero qué se construyó y para qué; luego cómo (tecnologías); por último el aporte del estudiante, si se conoce.\n"
    "- Si el proyecto fue en equipo usa «Participó en» o «Colaboró en»; nunca atribuyas todo el trabajo al estudiante.\n"
    "- Entrega exactamente {count} viñeta(s).\n"
    'Responde únicamente un objeto JSON: {{"vinetas": [str]}}'
)

SOFT_SKILLS_SYSTEM = (
    "Eres un redactor de currículums. Recibes señales verificables de la evidencia del estudiante "
    "y redactas habilidades blandas respaldadas por ellas.\n" + _COMMON_RULES +
    "- Solo puedes usar los identificadores de señal recibidos; no agregues otras habilidades.\n"
    "- Cada «frase» tiene máximo 15 palabras y describe la habilidad apoyándose en la señal.\n"
    'Responde únicamente un objeto JSON: {"habilidades": [{"id": str, "frase": str}]}'
)

COMPETENCIES_SYSTEM = (
    "Eres un redactor de currículums. Agrupas lo que el estudiante demostró en sus proyectos en "
    "3 a 5 competencias clave para el puesto.\n" + _COMMON_RULES +
    "- «titulo»: 2 a 4 palabras. «descripcion»: una frase de máximo 25 palabras que cite lo hecho en los proyectos.\n"
    'Responde únicamente un objeto JSON: {"competencias": [{"titulo": str, "descripcion": str}]}'
)

# --- Habilidades blandas respaldadas por evidencia -----------------------------------------------------------
_SOFT_LABELS = {
    "trabajo_en_equipo": ("Trabajo en equipo", "Colaboró en proyectos grupales de la carrera."),
    "comunicacion": ("Comunicación", "Presentó sus proyectos mediante presentaciones o video."),
    "documentacion": ("Documentación técnica", "Documentó sus entregas con reportes y archivos README."),
    "aprendizaje": ("Aprendizaje continuo", "Trabajó con varios lenguajes de programación en distintas materias."),
}


@dataclass
class SoftSignal:
    description: str  # lo que ve el modelo
    projects: list[str] = field(default_factory=list)  # claves de proyecto que la respaldan


@dataclass
class Drafted:
    """Texto redactado más los avisos que el usuario debe revisar."""

    text: str
    notes: list[str] = field(default_factory=list)


def _clean(text: object) -> str:
    return strip_numbers(str(text or "").strip())


class ResumeWriter:
    """Redacta las secciones con IA; si no hay modelo o falla, usa texto armado con reglas."""

    def __init__(self, model: LanguageModel | None) -> None:
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model.name if self._model else "sin modelo"

    def _ask(self, system: str, prompt: str) -> dict | None:
        if self._model is None:
            return None
        try:
            return self._model.complete_json(system, prompt)
        except Exception as exc:  # el modelo puede fallar de muchas formas; nunca detiene el currículum
            log.warning("Sección con modelo falló: %s", exc.__class__.__name__)
            return None

    # --- Resumen profesional / objetivo ---------------------------------------------------------------
    def intro(self, template: ResumeTemplate, role: JobRole, ranked: list[RankedProject]) -> Drafted:
        data = self._ask(INTRO_SYSTEM.format(focus=template.intro_focus), self._intro_prompt(role, ranked))
        text = _clean(data.get("texto")) if data else ""
        if text:
            return Drafted(text)
        return Drafted(self._intro_fallback(template, role, ranked),
                       ["Redactado sin modelo de lenguaje: personalízalo con tus palabras."])

    @staticmethod
    def _intro_prompt(role: JobRole, ranked: list[RankedProject]) -> str:
        lines = [f"Puesto objetivo: {role.name}", "Proyectos del estudiante:"]
        for r in ranked:
            lines.append(_project_context(r))
        return "\n".join(lines) + "\n\nRedacta el texto."

    @staticmethod
    def _intro_fallback(template: ResumeTemplate, role: JobRole, ranked: list[RankedProject]) -> str:
        languages = _top_languages(ranked)
        stack = f" con experiencia en {_join(languages[:4])}" if languages else ""
        if template.key == "practicas":
            return (f"Estudiante en busca de prácticas profesionales como {role.name}{stack}, "
                    "con proyectos académicos desarrollados y disposición para aprender.")
        return f"Estudiante orientado a {role.name}{stack}, con proyectos académicos relacionados con el puesto."

    # --- Viñetas por proyecto ----------------------------------------------------------------------------
    def bullets(self, template: ResumeTemplate, ranked: RankedProject) -> list[str]:
        system = BULLETS_SYSTEM.format(count=template.bullets_per_project)
        data = self._ask(system, _project_context(ranked) + "\n\nRedacta las viñetas.")
        raw = data.get("vinetas") if data else None
        if isinstance(raw, str):
            raw = [raw]
        items = [_clean(b) for b in raw] if isinstance(raw, list) else []
        items = [b for b in items if b][: template.bullets_per_project]
        if items:
            return items
        profile = ranked.candidate.profile
        return [profile.summary] if profile and profile.summary else []

    # --- Competencias (plantilla funcional) -------------------------------------------------------------------
    def competencies(self, role: JobRole, ranked: list[RankedProject]) -> Drafted:
        prompt = f"Puesto objetivo: {role.name}\nProyectos del estudiante:\n" + "\n".join(_project_context(r) for r in ranked)
        data = self._ask(COMPETENCIES_SYSTEM, prompt + "\n\nAgrupa las competencias.")
        raw = data.get("competencias") if data else None
        lines = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            title, desc = _clean(item.get("titulo")), _clean(item.get("descripcion"))
            if title:
                lines.append(f"- **{title}:** {desc}" if desc else f"- **{title}**")
        if lines:
            return Drafted("\n".join(lines[:5]))
        skills = Counter(s for r in ranked if r.candidate.profile for s in r.candidate.profile.skills)
        fallback = [f"- **{name}**" for name, _ in skills.most_common(5)]
        if not fallback:
            fallback = [f"- **{lang}**" for lang in _top_languages(ranked)[:5]]
        return Drafted("\n".join(fallback), ["Competencias sin modelo de lenguaje: agrega una descripción a cada una."])

    # --- Habilidades blandas ---------------------------------------------------------------------------------------
    def soft_skills(self, signals: dict[str, SoftSignal]) -> list[tuple[str, str, list[str]]]:
        """Devuelve (nombre, frase, proyectos que la respaldan). Solo señales con evidencia."""
        if not signals:
            return []
        prompt = "Señales verificables:\n" + "\n".join(f"- {sid}: {s.description}" for sid, s in signals.items())
        data = self._ask(SOFT_SKILLS_SYSTEM, prompt + "\n\nRedacta las habilidades.")
        phrases: dict[str, str] = {}
        raw = data.get("habilidades") if data else None
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, dict) and item.get("id") in signals:
                phrase = _clean(item.get("frase"))
                if phrase:
                    phrases[str(item["id"])] = phrase
        return [
            (_SOFT_LABELS[sid][0], phrases.get(sid) or _SOFT_LABELS[sid][1], sig.projects)
            for sid, sig in signals.items()
        ]


# --- Utilidades de contexto ------------------------------------------------------------------------------------------

def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def _top_languages(ranked: list[RankedProject]) -> list[str]:
    lines: Counter[str] = Counter()
    for r in ranked:
        for lang, stat in r.candidate.facts.languages.items():
            lines[lang] += stat.lines
    return [lang for lang, _ in lines.most_common()]


def _project_context(ranked: RankedProject) -> str:
    entry, facts, profile = ranked.candidate.entry, ranked.candidate.facts, ranked.candidate.profile
    parts = [f"- Proyecto «{entry.assignment_name}» (materia: {entry.course_name})"
             + (" [PROYECTO EN EQUIPO]" if entry.is_group else "")]
    if profile:
        if profile.summary:
            parts.append(f"  Resumen: {profile.summary}")
        if profile.technologies:
            parts.append(f"  Tecnologías: {', '.join(profile.technologies)}")
        if profile.skills:
            parts.append(f"  Habilidades: {', '.join(profile.skills)}")
        if profile.scope:
            parts.append(f"  Alcance: {profile.scope}")
    if facts.languages:
        parts.append(f"  Lenguajes: {', '.join(sorted(facts.languages))}")
    docs = sorted({d.kind for d in facts.documents})
    if docs:
        parts.append(f"  Documentos entregados: {', '.join(docs)}")
    return "\n".join(parts)


def _url(value: str) -> str:
    value = value.strip()
    return value if value.startswith(("http://", "https://")) else f"https://{value}"


# --- Armado del currículum --------------------------------------------------------------------------------------------------

class ResumeBuilder:
    """Convierte los proyectos rankeados en un currículum Markdown según la plantilla."""

    def __init__(self, writer: ResumeWriter, phraser: FactsPhraser | None = None) -> None:
        self._writer = writer
        self._phraser = phraser or FactsPhraser()

    def build(self, user: UserInfo, contact: ContactInfo, role: JobRole,
              template: ResumeTemplate, ranked: list[RankedProject]) -> str:
        context = _Context(user, contact, role, template, ranked)
        renderers = {
            "header": self._header,
            "summary": lambda c: self._intro(c, "Resumen profesional"),
            "objective": lambda c: self._intro(c, "Objetivo profesional"),
            "competencies": self._competencies,
            "projects": self._projects,
            "hard_skills": self._hard_skills,
            "soft_skills": self._soft_skills,
            "education": self._education,
        }
        blocks = [renderers[s](context) for s in template.sections]
        return "\n".join(line for block in blocks for line in block).rstrip() + "\n"

    # --- Secciones ---------------------------------------------------------------------------------------------------
    def _header(self, c: "_Context") -> list[str]:
        out = [f"# {c.user.name or 'Tu nombre'}", "", f"**{c.role.name}**", ""]
        reach = [x for x in (c.user.email, c.contact.phone.strip(), c.contact.location.strip()) if x]
        if reach:
            out += ["  ·  ".join(reach), ""]
        links = [f"[{label}]({_url(value)})" for label, value in
                 (("LinkedIn", c.contact.linkedin), ("GitHub", c.contact.github), ("Portafolio", c.contact.portfolio))
                 if value.strip()]
        if links:
            out += ["  ·  ".join(links), ""]
        missing = [label for label, value in (("LinkedIn", c.contact.linkedin), ("GitHub", c.contact.github)) if not value.strip()]
        if missing or not c.contact.phone.strip():
            out += [f"⚠ **Verificar:** agrega {', '.join(missing + (['teléfono'] if not c.contact.phone.strip() else []))} "
                    "en Configuración › Datos del currículum (o escríbelo aquí).", ""]
        return out

    def _intro(self, c: "_Context", title: str) -> list[str]:
        drafted = self._writer.intro(c.template, c.role, c.ranked)
        out = [f"## {title}", "", drafted.text, ""]
        out += [f"⚠ **Verificar:** {n}" for n in drafted.notes]
        return out + ([""] if drafted.notes else [])

    def _competencies(self, c: "_Context") -> list[str]:
        drafted = self._writer.competencies(c.role, c.ranked)
        out = ["## Competencias clave", "", drafted.text, ""]
        if drafted.notes:
            out += [f"⚠ **Verificar:** {n}" for n in drafted.notes] + [""]
        return out

    def _projects(self, c: "_Context") -> list[str]:
        out = ["## Proyectos", ""]
        if not c.ranked:
            return out + ["_No se encontraron proyectos afines a este puesto con los filtros elegidos._", ""]
        for r in c.ranked:
            entry, facts, profile = r.candidate.entry, r.candidate.facts, r.candidate.profile
            tag = " · **Proyecto en equipo**" if entry.is_group else ""
            out += [f"### {entry.assignment_name}", f"*{entry.course_name}* · {entry.submitted_at[:10] or 'sin fecha'}{tag}", ""]
            files = tuple((profile.sources if profile else [])[:3]) or tuple(facts.evidence_files[:3])
            for text in self._writer.bullets(c.template, r):
                out.append(f"- {text} {_evidence(entry.key, files)}")
            technologies = list(dict.fromkeys((profile.technologies if profile else []) or sorted(facts.languages)))
            if technologies:
                tech_files = tuple(facts.dependency_files[:3] + facts.code_files[:1]) or files
                out.append(f"- **Stack:** {', '.join(technologies)} {_evidence(entry.key, tech_files)}")
            code = self._phraser.code_line(facts)
            if code and facts.code_files and c.template.bullets_per_project > 1:
                out.append(f"- {code.removeprefix('Código entregado: ')} {_evidence(entry.key, tuple(facts.code_files[:3]))}")
            for link in facts.links:
                if link.kind in ("repositorio", "figma", "youtube", "drive"):
                    out.append(f"- {link.kind.capitalize()}: {link.url}")
            for note in (profile.doubtful if profile else []):
                out.append(f"  - ⚠ **Verificar:** {note}")
            out.append("")
        return out

    def _hard_skills(self, c: "_Context") -> list[str]:
        lines: Counter[str] = Counter()
        projects: dict[str, list[str]] = {}
        techs: dict[str, str] = {}
        for r in c.ranked:
            for lang, stat in r.candidate.facts.languages.items():
                lines[lang] += stat.lines
                projects.setdefault(lang, []).append(r.candidate.entry.key)
            profile = r.candidate.profile
            for tech in (profile.technologies if profile else []) + r.candidate.facts.dependencies[:6]:
                techs.setdefault(tech.lower(), tech)
        if not lines and not techs:
            return []
        languages = [lang for lang, _ in lines.most_common()]
        lowered = {lang.lower() for lang in languages}
        tools = [t for k, t in techs.items() if k not in lowered][:12]
        keys = sorted({k for ks in projects.values() for k in ks})
        out = ["## Habilidades técnicas", ""]
        if languages:
            out.append(f"- **Lenguajes:** {', '.join(languages)}")
        if tools:
            out.append(f"- **Tecnologías y herramientas:** {', '.join(tools)}")
        out.append(f"<!-- evidencia: {', '.join(keys) or 'perfiles de proyecto'} -->")
        return out + [""]

    def _soft_skills(self, c: "_Context") -> list[str]:
        results = self._writer.soft_skills(_soft_signals(c.ranked))
        if not results:
            return []
        out = ["## Habilidades blandas", ""]
        for name, phrase, keys in results:
            out.append(f"- **{name}:** {phrase} <!-- evidencia: {', '.join(keys)} -->")
        return out + [""]

    def _education(self, c: "_Context") -> list[str]:
        courses = list(dict.fromkeys(r.candidate.entry.course_name for r in c.ranked))
        out = ["## Formación académica", ""]
        if courses:
            out += [f"- **Materias relevantes:** {', '.join(courses)}"]
        out += ["", "⚠ **Verificar:** agrega tu carrera, institución y fechas; Canvas no las entrega.", ""]
        return out


@dataclass
class _Context:
    user: UserInfo
    contact: ContactInfo
    role: JobRole
    template: ResumeTemplate
    ranked: list[RankedProject]


def _evidence(key: str, files: tuple[str, ...]) -> str:
    return f"<!-- evidencia: raw/{key} → {'; '.join(files)} -->"


def _soft_signals(ranked: list[RankedProject]) -> dict[str, SoftSignal]:
    """Señales verificables en la evidencia; sin señal no hay habilidad blanda."""
    signals: dict[str, SoftSignal] = {}

    def add(sid: str, description: str, key: str) -> None:
        signals.setdefault(sid, SoftSignal(description)).projects.append(key)

    for r in ranked:
        entry, facts = r.candidate.entry, r.candidate.facts
        if entry.is_group:
            add("trabajo_en_equipo", "Entregó proyectos grupales en la carrera.", entry.key)
        if any(d.kind == "pptx" for d in facts.documents) or any(link.kind == "youtube" for link in facts.links):
            add("comunicacion", "Entregó presentaciones o videos para exponer sus proyectos.", entry.key)
        if facts.has_readme or any(d.kind in ("pdf", "docx") for d in facts.documents):
            add("documentacion", "Entregó reportes o README que explican sus proyectos.", entry.key)
    languages = {lang for r in ranked for lang in r.candidate.facts.languages}
    if len(languages) >= 3:
        signals["aprendizaje"] = SoftSignal(
            "Usó varios lenguajes de programación en sus proyectos.", [r.candidate.entry.key for r in ranked]
        )
    return signals
