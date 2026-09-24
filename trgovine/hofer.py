from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from jedro.datumi import parse_range
from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean, nearest_text

# PDF je v JavaScriptu pregledovalnika Publitas, ne v <a>.
PDF_V_HTML = re.compile(r"https://[\w.-]*publitas\.com/[^\"'\\\s]+?\.pdf[^\"'\\\s]*")


class HoferStore(BaseStore):
    name = "hofer"
    label = "Hofer Slovenija"
    listing_url = "https://www.hofer.si/aktualni-letaki-in-brosure"
    # Akamai zavrne brskalniški User-Agent iz programa (403), odkritega pa ne.
    headers = {"User-Agent": "arhiv-letakov (+https://github.com/ttrampus/arhiv-letakov)",
               "Accept": "*/*"}

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        soup = self.soup(self.html(fetchers))

        viewers: list[tuple[str, str]] = []
        seen: set[str] = set()
        for link in soup.select('a[href*="letaki.hofer.si"]'):
            viewer_url = self.absolute(link["href"].split("/page/")[0], fetchers)
            if not viewer_url or viewer_url in seen:
                continue
            seen.add(viewer_url)

            card = link.find_parent("div", class_="cms-multilayout-teaser")
            title = clean(card.get_text(" ")) if card else nearest_text(link)
            title = title.replace("Prelistajte", "").strip()
            viewers.append((viewer_url, title or viewer_url.rsplit("/", 1)[-1]))

        self.log.info("najdenih pregledovalnikov: %s, iščem PDF", len(viewers))

        magazines: list[Magazine] = []
        for viewer_url, title in viewers:
            try:
                pdf_url = self._pdf_from_viewer(fetchers, viewer_url)
            except Exception as exc:
                self.log.warning("%s ni bilo mogoče razrešiti (%s)", viewer_url, exc)
                continue
            if not pdf_url:
                self.log.warning("na %s ni povezave na PDF", viewer_url)
                continue

            date_from, date_to = parse_range(title)
            magazines.append(
                self.magazine(
                    title,
                    file_url=pdf_url,
                    source_url=viewer_url,
                    date_from=date_from,
                    date_to=date_to,
                )
            )

        return magazines

    def _pdf_from_viewer(self, fetchers: Fetchers, viewer_url: str) -> str | None:
        html = self.html(fetchers, viewer_url)
        match = PDF_V_HTML.search(html)
        if not match:
            return None
        return self.absolute(_pocisti(match.group(0)), fetchers)


def _pocisti(url: str) -> str:
    """Iz naslova vrže ubežne znake, ki jih pusti JSON v HTML."""
    url = url.replace("\\u0026", "&").replace("&amp;", "&")
    deli = urlsplit(url)
    return urlunsplit((deli.scheme, deli.netloc, deli.path, deli.query, ""))
