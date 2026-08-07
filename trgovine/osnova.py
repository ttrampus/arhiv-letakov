from __future__ import annotations

import logging
import re
from importlib.util import find_spec
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jedro.povezava import Fetchers
from jedro.modeli import Magazine

_PARSER = "lxml" if find_spec("lxml") else "html.parser"


class BaseStore:
    name: str = ""
    label: str = ""
    listing_url: str = ""
    requires_browser: bool = False

    def __init__(self) -> None:
        self.log = logging.getLogger(f"stores.{self.name}")

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        raise NotImplementedError

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, _PARSER)

    def absolute(self, href: str) -> str:
        return urljoin(self.listing_url, href.strip())

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
