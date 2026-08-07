from __future__ import annotations

import re

from jedro.datumi import parse_range
from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean

NOT_A_FLYER = re.compile(
    r"(pravilnik|splosni|splošni|prodajni-pogoji|pogoji|gdpr|izjava)", re.IGNORECASE
)


class LeclercStore(BaseStore):
    name = "leclerc"
    label = "E.Leclerc"
    listing_url = "https://www.e-leclerc.si/category/katalogi/vsi-katalogi/"

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        soup = self.soup(fetchers.http.get_html(self.listing_url))
        magazines: list[Magazine] = []
        seen: set[str] = set()

        for item in soup.select("ul.list li, div.com_catalog li"):
            pdf_link = item.select_one('a[href$=".pdf"]')
            if not pdf_link:
                continue

            file_url = self.absolute(pdf_link["href"])
            if file_url in seen or NOT_A_FLYER.search(file_url):
                continue
            seen.add(file_url)

            heading = item.select_one("h6 span, h6, h2")
            title = clean(heading.get_text()) if heading else "Katalog E.Leclerc"

            validity = item.select_one("p.validity")
            date_from, date_to = parse_range(
                clean(validity.get_text()) if validity else clean(item.get_text(" "))
            )

            viewer = item.select_one('a[href*="/pregledovalnik/"]')
            magazines.append(
                self.magazine(
                    title,
                    file_url=file_url,
                    source_url=self.absolute(viewer["href"]) if viewer else self.listing_url,
                    date_from=date_from,
                    date_to=date_to,
                )
            )

        return magazines
