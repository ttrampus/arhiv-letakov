import unittest
from datetime import date

from jedro.modeli import Magazine, slugify


class Slug(unittest.TestCase):
    def test_sumniki_in_presledki(self):
        self.assertEqual(slugify("Katalog Tuš, od 5. 8."), "katalog-tus-od-5-8")

    def test_skrajsa(self):
        self.assertEqual(len(slugify("a" * 200)), 80)

    def test_prazno_ime(self):
        self.assertEqual(slugify("!!!"), "katalog")


class Katalog(unittest.TestCase):
    def test_ime_datoteke(self):
        magazine = Magazine(store="tus", title="Akcijski katalog", source_url="",
                            file_url="http://x/a.pdf", date_from=date(2026, 8, 5))
        self.assertEqual(magazine.filename(), "2026-08-05_akcijski-katalog.pdf")
        self.assertEqual(magazine.year(), 2026)
        self.assertEqual(magazine.kind, "pdf")

    def test_kljuc_je_naslov_datoteke(self):
        magazine = Magazine(store="x", title="t", source_url="http://s",
                            file_url="http://x/a.pdf")
        self.assertEqual(magazine.dedupe_key, "http://x/a.pdf")

    def test_kljuc_pri_slikah_steje_strani(self):
        magazine = Magazine(store="x", title="t", source_url="http://s",
                            image_urls=["a", "b", "c"])
        self.assertEqual(magazine.dedupe_key, "http://s#3p")
        self.assertEqual(magazine.kind, "slike")

    def test_opis(self):
        magazine = Magazine(store="x", title="Letak", source_url="", file_url="u",
                            date_from=date(2026, 8, 1))
        self.assertEqual(magazine.describe(), "Letak [2026-08-01 .. ?] (pdf)")
