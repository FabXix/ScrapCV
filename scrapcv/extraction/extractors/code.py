"""Código suelto (CAR-08): lenguajes, líneas, dependencias y README."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from scrapcv.domain.facts import DocumentStat, Flag, TextSnippet
from scrapcv.extraction.base import CodeFileStat, ExtractionContext, ExtractionResult, FormatExtractor

MAX_CODE_BYTES = 2 * 1024 * 1024  # un archivo de código más grande suele ser generado

LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++",
    ".hpp": "C++", ".cs": "C#", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".dart": "Dart", ".scala": "Scala", ".r": "R", ".jl": "Julia", ".lua": "Lua", ".hs": "Haskell",
    ".sql": "SQL", ".sh": "Shell", ".ps1": "PowerShell", ".html": "HTML", ".css": "CSS", ".scss": "CSS",
    ".vue": "Vue", ".svelte": "Svelte", ".vhd": "VHDL", ".vhdl": "VHDL", ".v": "Verilog", ".asm": "Assembly",
    ".s": "Assembly", ".m": "MATLAB",
}

ENTRY_POINTS = {
    "main.py", "app.py", "__main__.py", "manage.py", "index.js", "main.js", "app.js", "server.js",
    "app.jsx", "app.tsx", "main.ts", "index.ts", "main.java", "main.c", "main.cpp", "main.go",
    "program.cs", "main.rs", "main.kt", "main.dart",
}

def read_text(path: Path, limit: int | None = None) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(limit) if limit else handle.read()


def head(text: str, lines: int) -> str:
    return "\n".join(text.splitlines()[:lines])


class SourceCodeExtractor(FormatExtractor):
    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in LANGUAGES

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        label = ctx.label(path)
        result = ExtractionResult()
        if path.stat().st_size > MAX_CODE_BYTES:
            result.flags.append(Flag(label, "archivo de código demasiado grande; se omitió del conteo"))
            return result
        text = read_text(path)
        lines = sum(1 for line in text.splitlines() if line.strip())
        result.code.append(CodeFileStat(LANGUAGES[path.suffix.lower()], lines, label))
        is_entry = path.name.lower() in ENTRY_POINTS
        result.snippets.append(TextSnippet(label, head(text, 60 if is_entry else 25), 3 if is_entry else 7))
        return result


class ReadmeExtractor(FormatExtractor):
    def can_handle(self, path: Path) -> bool:
        return path.stem.lower() in ("readme", "leeme", "léame") and path.suffix.lower() in ("", ".md", ".txt", ".rst")

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        text = read_text(path, 20000)
        label = ctx.label(path)
        return ExtractionResult(
            readme=True,
            documents=[DocumentStat(label, "readme", len(text.strip()))],
            snippets=[TextSnippet(label, text[:3000], 1)],
        )


class DependencyManifestExtractor(FormatExtractor):
    """Lee los manifiestos de dependencias más comunes."""

    _PARSERS = {
        "requirements.txt": "_requirements",
        "package.json": "_package_json",
        "pyproject.toml": "_pyproject",
        "pom.xml": "_pom",
        "build.gradle": "_gradle",
        "build.gradle.kts": "_gradle",
        "go.mod": "_go_mod",
        "cargo.toml": "_cargo",
        "composer.json": "_composer",
        "gemfile": "_gemfile",
    }

    def can_handle(self, path: Path) -> bool:
        return path.name.lower() in self._PARSERS or path.suffix.lower() == ".csproj"

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        text = read_text(path, 200_000)
        parser = "_csproj" if path.suffix.lower() == ".csproj" else self._PARSERS[path.name.lower()]
        deps = sorted({d.strip() for d in getattr(self, parser)(text) if d and d.strip()})
        label = ctx.label(path)
        return ExtractionResult(dependencies=deps, snippets=[TextSnippet(label, head(text, 40), 2)])

    @staticmethod
    def _requirements(text: str) -> list[str]:
        names = []
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith("-"):
                names.append(re.split(r"[<>=!~\[;\s]", line, maxsplit=1)[0])
        return names

    @staticmethod
    def _package_json(text: str) -> list[str]:
        try:
            data = json.loads(text)
        except ValueError:
            return []
        return [*data.get("dependencies", {}), *data.get("devDependencies", {})]

    @staticmethod
    def _composer(text: str) -> list[str]:
        try:
            data = json.loads(text)
        except ValueError:
            return []
        return [name for name in data.get("require", {}) if name != "php"]

    @staticmethod
    def _pyproject(text: str) -> list[str]:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return []
        deps = data.get("project", {}).get("dependencies", [])
        poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        names = [re.split(r"[<>=!~\[;\s]", d, maxsplit=1)[0] for d in deps]
        return names + [n for n in poetry if n.lower() != "python"]

    @staticmethod
    def _pom(text: str) -> list[str]:
        return re.findall(r"<dependency>.*?<artifactId>\s*([^<\s]+)\s*</artifactId>", text, flags=re.DOTALL)

    @staticmethod
    def _gradle(text: str) -> list[str]:
        return [m.split(":")[1] for m in re.findall(r"['\"]([\w.\-]+:[\w.\-]+)(?::[^'\"]*)?['\"]", text)]

    @staticmethod
    def _go_mod(text: str) -> list[str]:
        return re.findall(r"^\s*([\w./\-]+\.[\w./\-]+)\s+v[\d.]+", text, flags=re.MULTILINE)

    @staticmethod
    def _cargo(text: str) -> list[str]:
        try:
            return list(tomllib.loads(text).get("dependencies", {}))
        except tomllib.TOMLDecodeError:
            return []

    @staticmethod
    def _gemfile(text: str) -> list[str]:
        return re.findall(r"^\s*gem\s+['\"]([^'\"]+)['\"]", text, flags=re.MULTILINE)

    @staticmethod
    def _csproj(text: str) -> list[str]:
        return re.findall(r"<PackageReference\s+Include=\"([^\"]+)\"", text)

