"""Políticas de qué se lee y qué no.

- `CredentialPolicy` (CAR-19): archivos que nunca se abren ni se envían al modelo.
- `IgnoredFolderPolicy`: carpetas de terceros o generadas que inflarían las cifras.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

SENSITIVE_PATTERNS = (
    ".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*.ppk",
    "credentials*", "secrets*", "secret.*", "*.secret", ".npmrc", ".pypirc", ".netrc",
    "service-account*.json", "*token*.json", ".htpasswd", "*.kdbx",
)

IGNORED_FOLDERS = frozenset({
    "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", "target",
    "bin", "obj", ".idea", ".vscode", ".gradle", ".next", ".mypy_cache", ".pytest_cache",
    "__MACOSX", ".git",
})


class CredentialPolicy:
    def __init__(self, patterns: tuple[str, ...] = SENSITIVE_PATTERNS) -> None:
        self._patterns = patterns

    def is_sensitive(self, path: Path) -> bool:
        name = path.name.lower()
        return any(fnmatch.fnmatch(name, pattern) for pattern in self._patterns)


class IgnoredFolderPolicy:
    def __init__(self, folders: frozenset[str] = IGNORED_FOLDERS) -> None:
        self._folders = folders

    def is_ignored(self, folder: Path) -> bool:
        return folder.name in self._folders
