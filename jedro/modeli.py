from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Magazine:
    store: str
    title: str
    source_url: str
    file_url: str | None = None
    image_urls: list[str] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None

    @property
    def kind(self) -> str:
        return "pdf" if self.file_url else "slike"

    @property
    def dedupe_key(self) -> str:
        return self.file_url or f"{self.source_url}#{len(self.image_urls)}p"

    def filename(self) -> str:
        prefix = (self.date_from or date.today()).isoformat()
        return f"{prefix}_{slugify(self.title)}.pdf"

    def year(self) -> int:
        return (self.date_from or date.today()).year

    def describe(self) -> str:
        span = f" [{self.date_from} .. {self.date_to or '?'}]" if self.date_from else ""
        return f"{self.title}{span} ({self.kind})"


def slugify(text: str, max_length: int = 80) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug[:max_length] or "katalog"
