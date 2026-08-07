from __future__ import annotations

from jedro.datumi import parse_range
from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean, nearest_text


class TemplateStore(BaseStore):
    name = "predloga"
    label = "Ime trgovine"
    listing_url = "https://www.example.si/katalogi/"
    requires_browser = False

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        html = fetchers.http.get_html(self.listing_url)
        soup = self.soup(html)

        magazines: list[Magazine] = []
        for item in soup.select("li.catalog-item"):
            pdf_link = item.select_one('a[href$=".pdf"]')
            if not pdf_link:
                continue

            heading = item.select_one("h3, h4")
            title = clean(heading.get_text()) if heading else "Katalog"

            date_from, date_to = parse_range(nearest_text(pdf_link))

            magazines.append(
                self.magazine(
                    title,
                    file_url=self.absolute(pdf_link["href"]),
                    source_url=self.listing_url,
                    date_from=date_from,
                    date_to=date_to,
                )
            )

        return magazines
