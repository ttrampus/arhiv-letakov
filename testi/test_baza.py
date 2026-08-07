import tempfile
import unittest
from datetime import date
from pathlib import Path

from jedro.baza import Archive
from jedro.modeli import Magazine


def katalog(store="tus", file_url="http://x/a.pdf"):
    return Magazine(store=store, title="Akcijski katalog", source_url="http://x",
                    file_url=file_url, date_from=date(2026, 8, 5))


class Kazalo(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Archive(Path(self.temp.name) / "arhiv.db")
        self.addCleanup(self.archive.close)

    def test_zapis_in_iskanje(self):
        magazine = katalog()
        self.assertFalse(self.archive.has_url(magazine.dedupe_key))
        self.assertTrue(self.archive.record(magazine, Path("/tmp/a.pdf"), "abc", 10))
        self.assertTrue(self.archive.has_url(magazine.dedupe_key))
        self.assertTrue(self.archive.has_hash("abc"))

    def test_ista_vsebina_se_ne_zapise_dvakrat(self):
        self.archive.record(katalog(), Path("/tmp/a.pdf"), "abc", 10)
        self.assertFalse(
            self.archive.record(katalog(file_url="http://x/b.pdf"),
                                Path("/tmp/b.pdf"), "abc", 10))

    def test_povzetek(self):
        self.archive.record(katalog(), Path("/tmp/a.pdf"), "abc", 10)
        self.archive.record(katalog(store="spar", file_url="http://x/c.pdf"),
                            Path("/tmp/c.pdf"), "cde", 10)
        self.assertEqual([r["store"] for r in self.archive.summary()], ["spar", "tus"])

    def test_brisanje(self):
        self.archive.record(katalog(), Path("/tmp/a.pdf"), "abc", 10)
        row_id = self.archive.id_for_path("/tmp/a.pdf")
        self.archive.record_meat_version(row_id, Path("/tmp/m.pdf"), 20, 5)
        self.archive.delete(row_id)
        self.assertEqual(self.archive.all_rows(), [])
        self.assertEqual(self.archive.meat_summary(), [])

    def test_mesne_kopije_manjkajo(self):
        self.archive.record(katalog(), Path("/tmp/a.pdf"), "abc", 10)
        self.assertEqual(len(self.archive.magazines_without_meat_version()), 1)
        self.archive.record_meat_version(self.archive.id_for_path("/tmp/a.pdf"),
                                         Path("/tmp/m.pdf"), 20, 5)
        self.assertEqual(self.archive.magazines_without_meat_version(), [])


class StanjeTrgovin(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Archive(Path(self.temp.name) / "arhiv.db")
        self.addCleanup(self.archive.close)

    def test_neuspehi_se_stejejo(self):
        counts = [self.archive.note_store_result("spar", False, "nič najdenega")
                  for _ in range(3)]
        self.assertEqual(counts, [1, 2, 3])

    def test_prag_javi_samo_dovolj_pokvarjene(self):
        self.archive.note_store_result("spar", False, "nič")
        self.assertEqual(self.archive.failing_stores(3), [])
        self.archive.note_store_result("spar", False, "nič")
        self.archive.note_store_result("spar", False, "nič")
        rows = self.archive.failing_stores(3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "nič")

    def test_uspeh_pobrise_stevec(self):
        for _ in range(4):
            self.archive.note_store_result("spar", False, "nič")
        self.archive.note_store_result("spar", True)
        self.assertEqual(self.archive.failing_stores(1), [])

    def test_trgovine_so_locene(self):
        for _ in range(3):
            self.archive.note_store_result("spar", False, "nič")
        self.archive.note_store_result("lidl", True)
        self.assertEqual([r["store"] for r in self.archive.failing_stores(3)], ["spar"])
