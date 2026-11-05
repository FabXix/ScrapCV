"""Detección y clasificación de enlaces (CAR-11, CAR-16). Solo se registran."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from scrapcv.domain.facts import LinkRef

_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

_KINDS = (
    ("repositorio", ("github.com", "gitlab.com", "bitbucket.org")),
    ("drive", ("drive.google.com", "docs.google.com", "onedrive.live.com", "1drv.ms", "sharepoint.com")),
    ("figma", ("figma.com",)),
    ("youtube", ("youtube.com", "youtu.be")),
)


class LinkClassifier:
    def classify(self, url: str) -> str:
        host = (urlparse(url).hostname or "").lower()
        for kind, domains in _KINDS:
            if any(host == d or host.endswith("." + d) for d in domains):
                return kind
        return "otro"

    def find(self, text: str, source: str) -> list[LinkRef]:
        seen: dict[str, LinkRef] = {}
        for match in _URL.findall(text):
            url = match.rstrip(".,;")
            seen.setdefault(url, LinkRef(url=url, kind=self.classify(url), source=source))
        return list(seen.values())
