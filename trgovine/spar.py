from __future__ import annotations

import re
from datetime import date

from jedro.datumi import parse_range
from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_JAVA_DATE = re.compile(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\b.*?\b(\d{4})\b")
_SLUG = re.compile(r"letak\.spar\.si/([^/]+)/")


class SparStore(BaseStore):
    name = "spar"
    label = "Spar Slovenija"
    listing_url = "https://www.spar.si/letak"

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        soup = self.soup(fetchers.http.get_html(self.listing_url))
        magazines: list[Magazine] = []
        seen: set[str] = set()

        items = soup.select(".flyer-teaser__download-item")
        if not items:
            items = [link.parent for link in soup.select('a[href*="getPdf.ashx"]')]

        for item in items:
            pdf_link = item.select_one('a[href*="getPdf.ashx"]')
            if not pdf_link:
                continue

            file_url = self.absolute(pdf_link["href"])
            if file_url in seen:
                continue
            seen.add(file_url)

            title_node = item.select_one(".flyer-teaser__download-item__title")
            title = clean(title_node.get_text(" ")) if title_node else ""
            slug_match = _SLUG.search(file_url)
            if not title and slug_match:
                title = slug_match.group(1).replace("-", " ").title()

            date_from, date_to = self._dates(item, title)

            magazines.append(
                self.magazine(
                    title or "Spar katalog",
                    file_url=file_url,
                    source_url=file_url.replace("getPdf.ashx", "ViewPdf.ashx"),
                    date_from=date_from,
                    date_to=date_to,
                )
            )

        return magazines

    def _dates(self, item, title: str) -> tuple[date | None, date | None]:
        stamps = [
            parsed
            for node in item.select("[sly-data-test]")
            if (parsed := _parse_java_date(node.get("sly-data-test", "")))
        ]
        if stamps:
            return min(stamps), max(stamps)
        return parse_range(clean(item.get_text(" ")) or title)


def _parse_java_date(value: str) -> date | None:
    match = _JAVA_DATE.search(value)
    if not match:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if not month:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(2)))
    except ValueError:
        return None
