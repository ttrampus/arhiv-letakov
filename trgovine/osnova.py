from __future__ import annotations

import logging
import re
from importlib.util import find_spec
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jedro.povezava import Fetchers
from jedro.modeli import Magazine
from jedro.naslovi import ZavrnjenNaslov, preveri

_PARSER = "lxml" if find_spec("lxml") else "html.parser"


class BaseStore:
    name: str = ""
    label: str = ""
    listing_url: str = ""
    headers: dict[str, str] = {}

    def __init__(self) -> None:
        self.log = logging.getLogger(f"stores.{self.name}")

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        raise NotImplementedError

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, _PARSER)

    def absolute(self, href: str, fetchers: Fetchers | None = None) -> str:
        """Absolutni naslov, če je gostitelj dovoljen, sicer prazen niz."""
        href = (href or "").strip()
        if not href:
            return ""
        url = urljoin(self.listing_url, href)
        try:
            if fetchers is not None:
                return fetchers.http.preveri(url, self.name)
            return preveri(url, self.name)
        except ZavrnjenNaslov as exc:
            self.log.warning("povezavo preskočim: %s", exc)
            return ""

    def html(self, fetchers: Fetchers, url: str | None = None, **kwargs) -> str:
        return self.get(fetchers, url or self.listing_url, **kwargs).text

    def json(self, fetchers: Fetchers, url: str, **kwargs):
        return self.get(fetchers, url, **kwargs).json()

    def get(self, fetchers: Fetchers, url: str, **kwargs):
        headers = {**self.headers, **(kwargs.pop("headers", None) or {})}
        return fetchers.http.get(url, store=self.name, headers=headers or None, **kwargs)

    def magazine(self, title: str, **kwargs) -> Magazine:
        return Magazine(store=self.name, title=clean(title), **kwargs)


def clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def nearest_text(node, max_hops: int = 4) -> str:
    current = node
    for _ in range(max_hops):
        current = current.parent
        if current is None:
            break
        text = clean(current.get_text(" "))
        if len(text) > 25:
            return text
    return clean(node.get_text(" "))
