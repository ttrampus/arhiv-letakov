"""Fuzz in časovne meje, ki morajo veljati vedno (deterministično seme).

Obsežnejša različica (milijon naslovov) je tekla ročno; tu je dovolj velik
vzorec, da regresijo ujame, a še vedno hiter.
"""

import random
import re
import time
import unittest
from urllib.parse import urlsplit

import requests
from urllib3.util import parse_url

from jedro import datumi, naslovi
from trgovine import spar

OSNOVE = [("https://www.lidl.si/l/sl/katalog/x", "lidl"),
          ("https://assets.leaflets.schwarz/leaflets/pdfs/a.pdf", "lidl"),
          ("https://letak.spar.si/katalog-3826/getPdf.ashx", "spar"),
          ("https://cdn.ipaper.io/iPaper/a/Download.pdf?token=x", "spar"),
          ("https://view.publitas.com/96384/1/pdfs/a.pdf", "hofer")]
VRIVKI = ["@", "\\", "%40", "#", "?", "/", ":", ".", "..", "[", "]", "%", "%2e", "%2f",
          "evil.com", "127.0.0.1", "@evil.com", ".evil.com", "。", "．", "＠",
          ":0", ":443", ":1", "%00", "\x00", "\t", "\n", " ", "xn--", "-", "'", '"', "<", "|"]


def mutiraj(r: random.Random, s: str) -> str:
    for _ in range(r.randrange(1, 4)):
        i = r.randrange(len(s) + 1)
        s = s[:i] + r.choice(VRIVKI) + s[i + r.randrange(2):]
    return s


class FuzzNaslovov(unittest.TestCase):
    def test_sprejeto_je_dovoljeno_za_vsak_razclenjevalnik(self):
        """Kar preveri() sprejme, mora urllib3 in requests razumeti kot isti,
        dovoljeni gostitelj - sicer bi razlika v razčlenjevanju obšla seznam."""
        r = random.Random(20260922)
        sprejetih = 0
        for _ in range(30000):
            osnova, store = r.choice(OSNOVE)
            url = mutiraj(r, osnova)
            try:
                ok = naslovi.preveri(url, store)
            except naslovi.ZavrnjenNaslov:
                continue
            sprejetih += 1
            dovoljeni = naslovi.gostitelji(store)
            h1 = (parse_url(ok).host or "").lower().rstrip(".")
            h2 = (urlsplit(requests.Request("GET", ok).prepare().url).hostname or "").lower()
            self.assertTrue(naslovi._gostitelj_ustreza(h1, dovoljeni), (url, ok, h1))
            self.assertTrue(naslovi._gostitelj_ustreza(h2.rstrip("."), dovoljeni), (url, ok, h2))
            self.assertIn(parse_url(ok).port, (None, 443))
        # Vzorec mora res preizkusiti sprejete naslove, ne le zavrnjenih.
        self.assertGreater(sprejetih, 1000)


class ReDoS(unittest.TestCase):
    """Izrazi, ki tečejo nad besedilom tujih strani, morajo biti linearni."""

    def meri(self, izraz: re.Pattern, besedilo: str) -> float:
        zacetek = time.perf_counter()
        for _ in izraz.finditer(besedilo):
            pass
        return time.perf_counter() - zacetek

    def test_locila_datuma(self):
        self.assertLess(self.meri(datumi._SEPARATORS, " " * 200_000), 1.0)

    def test_datum_java(self):
        self.assertLess(self.meri(spar._JAVA_DATE, "Aug 1 " * 30_000), 1.0)

    def test_parse_range_na_dolgem_besedilu(self):
        zacetek = time.perf_counter()
        datumi.parse_range("1 . " * 500_000)
        datumi.looks_like_range(" " * 500_000)
        self.assertLess(time.perf_counter() - zacetek, 1.0)


if __name__ == "__main__":
    unittest.main()
