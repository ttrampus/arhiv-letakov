from __future__ import annotations

from datetime import date

from jedro.datumi import parse_range
from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean


class TusStore(BaseStore):
    name = "tus"
    label = "Tuš"
    listing_url = "https://www.tus.si/katalogi/"

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        soup = self.soup(fetchers.http.get_html(self.listing_url))
        magazines = []
        seen = set()

        for item in soup.select("li.list-item, div.card-catalogue"):
            pdf_link = item.select_one('a[href*="/uploads/catalogues/"], a.pdf[href$=".pdf"]')
            if not pdf_link:
                continue

            file_url = self.absolute(pdf_link["href"])
            if file_url in seen:
                continue
            seen.add(file_url)

            heading = item.select_one("h3 a, h3")
            times = [t.get("datetime") for t in item.select("time[datetime]")]
            date_from = _iso(times[0]) if times else None
            date_to = _iso(times[1]) if len(times) > 1 else None
            if not date_from:
                date_from, date_to = parse_range(clean(item.get_text(" ")))

            detail = item.select_one('h3 a[href*="katalogi"]')
            magazines.append(self.magazine(
                clean(heading.get_text()) if heading else "Katalog",
                file_url=file_url,
                source_url=self.absolute(detail["href"]) if detail else self.listing_url,
                date_from=date_from,
                date_to=date_to))

        return magazines


def _iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None
