from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote

from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean

HOST = "https://digitalflyer.eurospin.it"
API = f"{HOST}/api/eurospin/eurospin-slovenia"
STORE = "eurospin-slovenija"
VIEWER = f"https://www.eurospin.si/smt-digitalflyer/trgovine/{STORE}"


class EurospinStore(BaseStore):
    name = "eurospin"
    label = "Eurospin Slovenija"
    listing_url = VIEWER
    requires_browser = True

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        browser = fetchers.browser
        token = browser.capture_request_header(VIEWER, "/api/eurospin", "authorization")
        if not token:
            self.log.warning("iz pregledovalnika letakov ni bilo mogoče ujeti žetona API")
            return []

        headers = {"Authorization": token}
        promotions = browser.api_get(f"{API}/stores/{STORE}/promotions", headers)
        if isinstance(promotions, dict):
            promotions = promotions.get("content") or promotions.get("data") or []
        self.log.info("najdenih akcij: %s", len(promotions))

        magazines: list[Magazine] = []
        for promotion in promotions:
            alias = promotion.get("alias")
            if not alias:
                continue
            title = clean(promotion.get("description")) or alias.replace("-", " ")
            date_from = _parse(promotion.get("startDate"))
            date_to = _parse(promotion.get("endDate"))

            try:
                contents = browser.api_get(
                    f"{API}/stores/{STORE}/promotions/{alias}"
                    f"/contents-light?typeCode=FLY&typeCode=FLT",
                    headers,
                )
            except Exception as exc:
                self.log.warning("za %s ni vsebine (%s)", alias, exc)
                continue

            for pdf_name, pdf_id in _pdf_files(contents):
                magazines.append(
                    self.magazine(
                        title,
                        file_url=f"{HOST}/files/{pdf_id}/{quote(pdf_name)}",
                        source_url=f"{VIEWER}/promocije/{alias}",
                        date_from=date_from,
                        date_to=date_to,
                    )
                )

        return magazines


def _pdf_files(contents: list[dict]) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for item in contents or []:
        if (item.get("type") or {}).get("code") != "FLY":
            continue
        for prop in item.get("properties") or []:
            if prop.get("code") != "PDF":
                continue
            for value in prop.get("values") or []:
                name, unique_id = value.get("name"), value.get("uniqueId")
                if name and unique_id:
                    files.append((name, unique_id))
    return files


def _parse(value: str | None) -> date | None:
    if not value or len(value) < 8:
        return None
    try:
        return datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError:
        return None
