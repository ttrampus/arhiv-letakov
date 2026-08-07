from __future__ import annotations

from jedro.datumi import parse_range
from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean, nearest_text


class MercatorStore(BaseStore):
    name = "mercator"
    label = "Mercator"
    listing_url = "https://www.mercator.si/katalogi/"

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        soup = self.soup(fetchers.http.get_html(self.listing_url))
        magazines = []

        for item in soup.select("li.catalog-item"):
            pdf_link = item.select_one('a[href$=".pdf"]')
            if not pdf_link:
                continue

            title_link = item.select_one("a.title-link") or item.select_one("h4 a, h4")
            title = clean(title_link.get_text()) if title_link else "Katalog"

            validity = item.select_one("p.small")
            date_from, date_to = parse_range(
                clean(validity.get_text()) if validity else nearest_text(pdf_link))
            if not date_from:
                date_from, date_to = parse_range(title)

            detail = item.select_one('a[href^="/katalogi/"]')
            magazines.append(self.magazine(
                title,
                file_url=self.absolute(pdf_link["href"]),
                source_url=self.absolute(detail["href"]) if detail else self.listing_url,
                date_from=date_from,
                date_to=date_to))

        return magazines
