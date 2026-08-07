from __future__ import annotations

from jedro.datumi import parse_range
from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean, nearest_text


class HoferStore(BaseStore):
    name = "hofer"
    label = "Hofer Slovenija"
    listing_url = "https://www.hofer.si/aktualni-letaki-in-brosure"
    requires_browser = True

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        browser = fetchers.browser
        soup = self.soup(browser.get_html(self.listing_url))

        viewers: list[tuple[str, str]] = []
        seen: set[str] = set()
        for link in soup.select('a[href*="letaki.hofer.si"]'):
            viewer_url = link["href"].split("/page/")[0].strip()
            if viewer_url in seen:
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
                pdf_url = self._pdf_from_viewer(browser, viewer_url)
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

    def _pdf_from_viewer(self, browser, viewer_url: str) -> str | None:
        soup = self.soup(browser.get_html(viewer_url, settle_ms=3000))
        link = soup.select_one('a[href*="/pdfs/"]')
        return link["href"] if link else None
