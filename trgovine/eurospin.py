from __future__ import annotations

import base64
import re
from datetime import date, datetime
from urllib.parse import quote

from jedro.povezava import Fetchers
from jedro.modeli import Magazine

from .osnova import BaseStore, clean

HOST = "https://digitalflyer.eurospin.it"
API = f"{HOST}/api/eurospin/eurospin-slovenia"
STORE = "eurospin-slovenija"
VIEWER = f"https://www.eurospin.si/smt-digitalflyer/trgovine/{STORE}"
BUNDLE = "https://www.eurospin.si/smt-digitalflyer/"

# Javna koda odjemalca OAuth iz JS pregledovalnika; zasilna, če je iz svežnja ne dobimo.
REZERVNA_KODA = "4f6d86bf-a34f-4830-8c5a-2d57c7ace364:HOJ3wseZ"
KODA_V_JS = re.compile(r"apiAuthorizationCode:\s*[\"']([^\"']+)[\"']")
SVEZENJ = re.compile(r'src="(/smt-digitalflyer/assets/index-[\w-]+\.js)"')


class EurospinStore(BaseStore):
    name = "eurospin"
    label = "Eurospin Slovenija"
    listing_url = VIEWER

    def find_magazines(self, fetchers: Fetchers) -> list[Magazine]:
        token = self._token(fetchers)
        if not token:
            self.log.warning("žetona za API ni bilo mogoče dobiti")
            return []

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        promotions = self.json(fetchers, f"{API}/stores/{STORE}/promotions", headers=headers)
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
                contents = self.json(
                    fetchers,
                    f"{API}/stores/{STORE}/promotions/{quote(alias, safe='')}"
                    f"/contents-light?typeCode=FLY&typeCode=FLT",
                    headers=headers)
            except Exception as exc:
                self.log.warning("za %s ni vsebine (%s)", alias, exc)
                continue

            for pdf_name, pdf_id in _pdf_files(contents):
                file_url = self.absolute(
                    f"{HOST}/files/{quote(pdf_id, safe='')}/{quote(pdf_name)}", fetchers)
                if not file_url:
                    continue
                magazines.append(
                    self.magazine(
                        title,
                        file_url=file_url,
                        source_url=f"{VIEWER}/promocije/{alias}",
                        date_from=date_from,
                        date_to=date_to,
                    )
                )

        return magazines

    def _token(self, fetchers: Fetchers) -> str | None:
        koda = self._koda(fetchers)
        osnova = base64.b64encode(koda.encode()).decode()
        response = fetchers.http.post(
            f"{HOST}/oauth/token", store=self.name,
            data={"grant_type": "client_credentials", "scope": "read write"},
            headers={"Authorization": f"Basic {osnova}", "Accept": "application/json"})
        return response.json().get("access_token")

    def _koda(self, fetchers: Fetchers) -> str:
        try:
            html = self.html(fetchers, BUNDLE)
            match = SVEZENJ.search(html)
            if match:
                js = self.html(fetchers, self.absolute(match.group(1), fetchers))
                found = KODA_V_JS.search(js)
                if found:
                    return found.group(1)
        except Exception as exc:
            self.log.debug("kode odjemalca ni bilo mogoče prebrati (%s)", exc)
        self.log.debug("uporabljam zasilno kodo odjemalca")
        return REZERVNA_KODA


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
