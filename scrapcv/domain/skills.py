"""Catálogo de tecnologías y competencias reconocibles.

Sirve para tres cosas:
- Encontrar requisitos técnicos en el texto de una vacante sin modelo de lenguaje.
- Comparar la vacante con la evidencia usando nombres canónicos («node» = «Node.js»).
- Agrupar las habilidades del CV por categoría y descartar dependencias que no
  dicen nada a un reclutador (``dotenv``, ``cors``…).

Agregar una tecnología es agregar una línea (OCP); nadie más cambia.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

LANGUAGES = "Lenguajes"
FRAMEWORKS = "Frameworks y librerías"
DATABASES = "Bases de datos"
TOOLS = "Herramientas y plataformas"
PRACTICES = "Metodologías y prácticas"
SOFT = "Competencias"
PROFESSIONAL = "Habilidades profesionales"  # lo que no es tecnología: análisis, planeación, redacción…

CATEGORY_ORDER = (LANGUAGES, FRAMEWORKS, DATABASES, TOOLS, PRACTICES)


@dataclass(frozen=True)
class Skill:
    name: str  # nombre como debe verse en el CV
    category: str
    aliases: tuple[str, ...] = ()  # formas en que aparece en vacantes o en dependencias

    @property
    def forms(self) -> tuple[str, ...]:
        return (normalize(self.name), *(normalize(a) for a in self.aliases))


def normalize(value: str) -> str:
    """Minúsculas y sin acentos, para comparar."""
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower().strip()


def _s(name: str, category: str, *aliases: str) -> Skill:
    return Skill(name, category, aliases)


# Los nombres de una letra o ambiguos en español (C, R, Go) solo se buscan con formas explícitas.
CATALOG: tuple[Skill, ...] = (
    # Lenguajes
    _s("Python", LANGUAGES, "python3"),
    _s("Java", LANGUAGES),
    _s("JavaScript", LANGUAGES, "js", "ecmascript"),
    _s("TypeScript", LANGUAGES, "ts"),
    _s("C#", LANGUAGES, "csharp", "c sharp"),
    _s("C++", LANGUAGES, "cpp"),
    _s("C", LANGUAGES, "lenguaje c", "ansi c", "c/c++"),
    _s("Go", LANGUAGES, "golang"),
    _s("Kotlin", LANGUAGES),
    _s("Swift", LANGUAGES),
    _s("PHP", LANGUAGES),
    _s("Ruby", LANGUAGES),
    _s("Rust", LANGUAGES),
    _s("R", LANGUAGES, "lenguaje r", "rstudio"),
    _s("Julia", LANGUAGES),
    _s("SQL", LANGUAGES, "t-sql", "pl/sql"),
    _s("HTML", LANGUAGES, "html5"),
    _s("CSS", LANGUAGES, "css3", "sass", "scss"),
    _s("Bash", LANGUAGES, "shell", "shell scripting"),
    _s("Dart", LANGUAGES),
    _s("VHDL", LANGUAGES),
    _s("Verilog", LANGUAGES),
    _s("Assembly", LANGUAGES, "ensamblador"),
    # Frameworks y librerías
    _s("Node.js", FRAMEWORKS, "node", "nodejs", "node js"),
    _s("Express", FRAMEWORKS, "express.js", "expressjs"),
    _s("React", FRAMEWORKS, "react.js", "reactjs", "react-dom"),
    _s("React Native", FRAMEWORKS, "react-native"),
    _s("Angular", FRAMEWORKS, "@angular/core"),
    _s("Vue", FRAMEWORKS, "vue.js", "vuejs"),
    _s("Svelte", FRAMEWORKS),
    _s("Next.js", FRAMEWORKS, "next", "nextjs"),
    _s("Tailwind CSS", FRAMEWORKS, "tailwind", "tailwindcss"),
    _s("Bootstrap", FRAMEWORKS),
    _s("Django", FRAMEWORKS),
    _s("Flask", FRAMEWORKS),
    _s("FastAPI", FRAMEWORKS),
    _s("Spring Boot", FRAMEWORKS, "spring", "spring-boot", "spring-boot-starter-web"),
    _s(".NET", FRAMEWORKS, "dotnet", "asp.net", ".net core"),
    _s("Laravel", FRAMEWORKS),
    _s("Flutter", FRAMEWORKS),
    _s("SQLAlchemy", FRAMEWORKS),
    _s("Mongoose", FRAMEWORKS),
    _s("Pandas", FRAMEWORKS),
    _s("NumPy", FRAMEWORKS),
    _s("scikit-learn", FRAMEWORKS, "sklearn", "scikit learn"),
    _s("TensorFlow", FRAMEWORKS, "keras"),
    _s("PyTorch", FRAMEWORKS, "torch"),
    _s("Matplotlib", FRAMEWORKS),
    _s("Seaborn", FRAMEWORKS),
    _s("JUnit", FRAMEWORKS, "junit-jupiter", "junit5"),
    _s("pytest", FRAMEWORKS),
    _s("Jest", FRAMEWORKS),
    _s("JWT", FRAMEWORKS, "jsonwebtoken", "json web token", "pyjwt"),
    _s("Socket.IO", FRAMEWORKS, "socket.io", "websockets", "websocket"),
    _s("Axios", FRAMEWORKS),
    _s("Vite", FRAMEWORKS),
    _s("GraphQL", FRAMEWORKS),
    # Bases de datos
    _s("MongoDB", DATABASES, "mongo", "pymongo"),
    _s("PostgreSQL", DATABASES, "postgres", "psycopg2", "pg"),
    _s("MySQL", DATABASES, "mysql2", "mariadb"),
    _s("SQLite", DATABASES, "sqlite3"),
    _s("SQL Server", DATABASES, "mssql", "microsoft sql server"),
    _s("Oracle Database", DATABASES, "oracle"),
    _s("Redis", DATABASES),
    _s("Firebase", DATABASES, "firestore"),
    _s("Cassandra", DATABASES),
    _s("Neo4j", DATABASES),
    _s("DynamoDB", DATABASES),
    # Herramientas y plataformas
    _s("Git", TOOLS, "github", "gitlab", "control de versiones"),
    _s("Docker", TOOLS, "dockerfile", "docker compose", "docker-compose", "contenedores"),
    _s("Kubernetes", TOOLS, "k8s"),
    _s("AWS", TOOLS, "amazon web services", "ec2", "s3", "lambda"),
    _s("Azure", TOOLS, "microsoft azure"),
    _s("Google Cloud", TOOLS, "gcp", "google cloud platform"),
    _s("Linux", TOOLS, "ubuntu"),
    _s("Postman", TOOLS),
    _s("Figma", TOOLS),
    _s("Jupyter", TOOLS, "jupyter notebook", "ipynb"),
    _s("Power BI", TOOLS, "powerbi"),
    _s("Tableau", TOOLS),
    _s("Excel", TOOLS),
    _s("Arduino", TOOLS),
    _s("FPGA", TOOLS),
    _s("Jira", TOOLS),
    _s("CI/CD", TOOLS, "github actions", "integracion continua", "jenkins"),
    # Metodologías y prácticas
    _s("API REST", PRACTICES, "rest", "restful", "api rest", "rest api", "apis rest", "servicios web"),
    _s("Programación orientada a objetos", PRACTICES, "poo", "oop", "orientada a objetos", "orientado a objetos"),
    _s("Patrones de diseño", PRACTICES, "patrones de diseno", "design patterns", "patron strategy", "strategy"),
    _s("Pruebas unitarias", PRACTICES, "unit testing", "pruebas automatizadas", "testing"),
    _s("Scrum", PRACTICES, "metodologias agiles", "agile", "agil", "kanban"),
    _s("UML", PRACTICES, "diagramas uml", "casos de uso"),
    _s("Ingeniería de requisitos", PRACTICES, "requisitos", "historias de usuario", "levantamiento de requerimientos",
       "requerimientos"),
    _s("Concurrencia", PRACTICES, "hilos", "multithreading", "programacion concurrente", "threads"),
    _s("Machine learning", PRACTICES, "aprendizaje automatico", "aprendizaje de maquina", "modelos predictivos"),
    _s("Análisis de datos", PRACTICES, "analisis de datos", "data analysis", "visualizacion de datos"),
    _s("Microservicios", PRACTICES, "microservices"),
    _s("Seguridad web", PRACTICES, "autenticacion", "autorizacion", "owasp", "bcrypt", "bcryptjs"),
    _s("Diseño UX/UI", PRACTICES, "ux", "ui", "experiencia de usuario", "prototipado", "prototipo"),
)

SOFT_SKILLS: tuple[Skill, ...] = (
    _s("Trabajo en equipo", SOFT, "trabajo colaborativo", "colaboracion", "team player", "teamwork"),
    _s("Comunicación", SOFT, "comunicacion efectiva", "habilidades de comunicacion", "communication"),
    _s("Documentación técnica", SOFT, "documentacion", "documentar"),
    _s("Aprendizaje continuo", SOFT, "ganas de aprender", "disposicion para aprender", "autodidacta"),
    _s("Resolución de problemas", SOFT, "solucion de problemas", "problem solving", "pensamiento analitico"),
    _s("Liderazgo", SOFT, "leadership"),
    _s("Proactividad", SOFT, "proactivo", "proactiva", "iniciativa"),
)

_BY_FORM: dict[str, Skill] = {}
for _skill in CATALOG + SOFT_SKILLS:
    for _form in _skill.forms:
        _BY_FORM.setdefault(_form, _skill)

# Formas que no conviene buscar sueltas en prosa: son palabras comunes o letras.
_PROSE_UNSAFE = {"c", "r", "go", "next", "ts", "js", "ui", "ux", "pg", "s3", "spring", "testing", "agil", "rest",
                 "strategy", "shell", "lambda", "node", "torch", "requisitos", "documentar", "documentacion",
                 "prototipo", "hilos", "oracle", "mongo", "github", "excel"}
# …salvo que el texto sea claramente una lista de requisitos de una línea (p. ej. «Node, Mongo, Git»).


def canonical(name: str) -> Skill | None:
    """Tecnología del catálogo para un nombre o alias (dependencia, lenguaje, requisito)."""
    key = normalize(name)
    if key in _BY_FORM:
        return _BY_FORM[key]
    base = re.split(r"[@\[<>=~^ ]", key.lstrip("@"), maxsplit=1)[0]  # «flask>=2.0», «@angular/core@17»
    return _BY_FORM.get(base) or _BY_FORM.get(key.split("/")[-1])


def find_in_text(text: str, include_soft: bool = True) -> list[Skill]:
    """Tecnologías mencionadas en un texto libre, en el orden en que aparecen."""
    normalized = " " + normalize(text) + " "
    found: list[tuple[int, Skill]] = []
    pool = CATALOG + (SOFT_SKILLS if include_soft else ())
    for skill in pool:
        positions = []
        for form in skill.forms:
            if form in _PROSE_UNSAFE and not _listed(form, normalized):
                continue
            match = re.search(r"(?<![a-z0-9+#])" + re.escape(form) + r"(?![a-z0-9+#])", normalized)
            if match:
                positions.append(match.start())
        if positions:
            found.append((min(positions), skill))
    return [skill for _, skill in sorted(found, key=lambda item: item[0])]


def _listed(form: str, text: str) -> bool:
    """La forma aparece como elemento de una lista («…, Go, …» / «Node.js / Go») o con mayúscula tecnológica."""
    escaped = re.escape(form)
    return bool(re.search(r"(?:^|[,;/•·(\n]|\by\b|\band\b)\s*" + escaped + r"\s*(?=$|[,;/•·)\n]|\by\b|\band\b)", text))


def is_soft(skill: Skill) -> bool:
    return skill.category == SOFT


# Una dependencia que solo existe sobre otra tecnología la demuestra también («express» ⇒ Node.js).
IMPLIES: dict[str, tuple[str, ...]] = {
    "Express": ("Node.js",),
    "Socket.IO": ("Node.js",),
    "Mongoose": ("MongoDB", "Node.js"),
    "Next.js": ("React",),
    "React Native": ("React",),
    "Django": ("Python",),
    "Flask": ("Python",),
    "FastAPI": ("Python",),
    "Spring Boot": ("Java",),
    "Laravel": ("PHP",),
    "Flutter": ("Dart",),
}


def with_implied(skills: list[Skill]) -> list[Skill]:
    out = list(skills)
    for skill in skills:
        for name in IMPLIES.get(skill.name, ()):
            implied = canonical(name)
            if implied and implied not in out:
                out.append(implied)
    return out
