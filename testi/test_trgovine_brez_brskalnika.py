"""Hofer in Eurospin sta prepisana na navaden HTTP; tu to preverimo brez omrežja.

Vzorca v testi/vzorci sta odrezka resničnih strani iz septembra 2026. Ko
trgovina prenovi stran, ta testa padeta prva - to je namen.
"""

import json
import unittest
from pathlib import Path

from trgovine.eurospin import EurospinStore
from trgovine.hofer import HoferStore

VZORCI = Path(__file__).parent / "vzorci"


class LaznaSeja:
    """Namesto omrežja vrne pripravljene odgovore."""

    def __init__(self, odgovori: dict):
        self.odgovori = odgovori
        self.klici = []

    def preveri(self, url, store):
        return url

    def get(self, url, store=None, **kwargs):
        self.klici.append(url)
        for kljuc, vsebina in self.odgovori.items():
            if kljuc in url:
                return Odgovor(vsebina)
        raise AssertionError(f"nepričakovana zahteva: {url}")

    def post(self, url, store=None, **kwargs):
        return self.get(url, store, **kwargs)

    def get_html(self, url, store=None, **kwargs):
        return self.get(url, store, **kwargs).text


class Odgovor:
    def __init__(self, vsebina):
        self._vsebina = vsebina

    @property
    def text(self):
        return (self._vsebina if isinstance(self._vsebina, str)
                else json.dumps(self._vsebina))

    def json(self):
        return (self._vsebina if not isinstance(self._vsebina, str)
                else json.loads(self._vsebina))


class LazniFetchers:
    def __init__(self, odgovori):
        self.http = LaznaSeja(odgovori)


class Hofer(unittest.TestCase):
    def setUp(self):
        self.fetchers = LazniFetchers({
            "aktualni-letaki": (VZORCI / "hofer-seznam.html").read_text(encoding="utf-8"),
            "letaki.hofer.si": (VZORCI / "hofer-pregledovalnik.html").read_text(
                encoding="utf-8"),
        })

    def test_najde_letake_brez_brskalnika(self):
        magazines = HoferStore().find_magazines(self.fetchers)
        self.assertTrue(magazines)
        for magazine in magazines:
            self.assertTrue(magazine.file_url.startswith("https://view.publitas.com/"))
            self.assertTrue(magazine.source_url.startswith("https://letaki.hofer.si/"))

    def test_naslov_pdf_nima_podpisanih_parametrov(self):
        magazine = HoferStore().find_magazines(self.fetchers)[0]
        self.assertTrue(magazine.file_url.endswith(".pdf"))

    def test_prvi_letak_ima_datum(self):
        magazines = HoferStore().find_magazines(self.fetchers)
        self.assertTrue(any(m.date_from for m in magazines))


class Eurospin(unittest.TestCase):
    ZETON = {"access_token": "test-zeton"}
    PROMOCIJE = [{"alias": "p22-2026", "description": "Velikani prihranka",
                  "startDate": "20260910000000", "endDate": "20260916000000"}]
    VSEBINA = [{"type": {"code": "FLY"},
                "properties": [{"code": "PDF",
                                "values": [{"name": "ESL-DOR_C.pdf",
                                            "uniqueId": "750d742c-ec52"}]}]}]

    def setUp(self):
        self.fetchers = LazniFetchers({
            "/oauth/token": self.ZETON,
            "/promotions/": self.VSEBINA,
            "/promotions": self.PROMOCIJE,
            "smt-digitalflyer": "<html></html>",
        })

    def test_najde_letake_prek_oauth(self):
        magazines = EurospinStore().find_magazines(self.fetchers)
        self.assertEqual(len(magazines), 1)
        magazine = magazines[0]
        self.assertEqual(
            magazine.file_url,
            "https://digitalflyer.eurospin.it/files/750d742c-ec52/ESL-DOR_C.pdf")
        self.assertEqual(str(magazine.date_from), "2026-09-10")

    def test_brez_zetona_ne_pade(self):
        self.fetchers = LazniFetchers({"/oauth/token": {},
                                       "smt-digitalflyer": "<html></html>"})
        self.assertEqual(EurospinStore().find_magazines(self.fetchers), [])

    def test_zeton_gre_v_glavo(self):
        EurospinStore().find_magazines(self.fetchers)
        self.assertTrue(any("/promotions" in url for url in self.fetchers.http.klici))


if __name__ == "__main__":
    unittest.main()
