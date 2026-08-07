from __future__ import annotations

import re
from datetime import date

from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean

API = "https://endpoints.leaflets.schwarz/v4/flyer"
SLUG_PATTERN = re.compile(r"/l/sl/katalog/([a-z0-9][a-z0-9-]+)")


class LidlStore(BaseStore):
    name = "lidl"
    label = "Lidl Slovenija"
    listing_url = "https://www.lidl.si/c/spletni-katalog/s10019133"

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        slugs = self._discover_slugs(fetchers)
        if not slugs:
            self.log.warning("na %s ni bilo najdenih oznak letakov", self.listing_url)
            return []
        self.log.info("najdenih oznak letakov: %s", len(slugs))

        magazines: dict[str, Magazine] = {}
        for slug in slugs:
            try:
                payload = fetchers.http.get(
                    API, params={"flyer_identifier": slug}, headers={"Accept": "application/json"}
                ).json()
            except Exception as exc:
                self.log.warning("poizvedba API za %s ni uspela (%s)", slug, exc)
                continue

            flyer = payload.get("flyer") if payload.get("success") else None
            if not flyer:
                self.log.warning("za %s ni podatkov o letaku", slug)
                continue

            for magazine in self._from_flyer(flyer):
                magazines.setdefault(magazine.file_url, magazine)

        return list(magazines.values())

    def _discover_slugs(self, fetchers: Fetchers) -> list[str]:
        slugs: list[str] = []
        for url in (self.listing_url, "https://www.lidl.si/"):
            try:
                html = fetchers.http.get_html(url)
            except Exception as exc:
                self.log.warning("ni bilo mogoče prebrati %s (%s)", url, exc)
                continue
            for slug in SLUG_PATTERN.findall(html):
                if slug not in slugs:
                    slugs.append(slug)
        return slugs

    def _from_flyer(self, flyer: dict) -> list[Magazine]:
        found: list[Magazine] = []

        pdf_url = flyer.get("pdfUrl") or flyer.get("hiResPdfUrl")
        if pdf_url:
            found.append(
                self.magazine(
                    _title(flyer),
                    file_url=pdf_url,
                    source_url=flyer.get("flyerUrlAbsolute") or self.listing_url,
                    date_from=_parse(flyer.get("startDate")),
                    date_to=_parse(flyer.get("endDate")),
                )
            )

        for related in flyer.get("relatedFlyers") or []:
            related_pdf = related.get("pdfUrl")
            if not related_pdf:
                continue
            found.append(
                self.magazine(
                    _title(related),
                    file_url=related_pdf,
                    source_url=related.get("url") or self.listing_url,
                    date_from=_parse(related.get("startDate")),
                    date_to=_parse(related.get("endDate")),
                )
            )

        return found


def _title(flyer: dict) -> str:
    parts = [clean(flyer.get("name")), clean(flyer.get("title"))]
    return " ".join(p for p in parts if p) or "Lidlov katalog"


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
