"""Obdelava PDF ne sme teči neomejeno dolgo ali čez poljubno veliko strani."""

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

from jedro import strani


def pdf_s_stranmi(path: Path, stevilo: int) -> Path:
    writer = PdfWriter()
    for _ in range(stevilo):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


class Meje(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vir = pdf_s_stranmi(self.root / "letak.pdf", 12)
        self.cilj = self.root / "meso" / "letak.pdf"

    def test_prevec_strani_se_zavrne(self):
        with self.assertRaises(strani.PrevelikPdf) as napaka:
            strani.filter_pdf(self.vir, self.cilj, use_ocr=False, max_pages=5)
        self.assertIn("12 strani", str(napaka.exception))
        self.assertFalse(self.cilj.exists())

    def test_izvirnik_ostane_nedotaknjen(self):
        with self.assertRaises(strani.PrevelikPdf):
            strani.filter_pdf(self.vir, self.cilj, use_ocr=False, max_pages=5)
        self.assertTrue(self.vir.exists())

    def test_pod_mejo_se_obdela(self):
        rezultat = strani.filter_pdf(self.vir, self.cilj, use_ocr=False, max_pages=50)
        self.assertEqual(rezultat.total, 12)
        # Prazne strani nimajo besedila, zato jih obdrži vse.
        self.assertEqual(len(rezultat.kept), 12)

    def test_potekel_cas_ne_vrze_izjeme(self):
        rezultat = strani.filter_pdf(self.vir, self.cilj, use_ocr=False,
                                     max_pages=50, budget_s=0)
        self.assertEqual(rezultat.total, 12)

    def test_brez_ocr_ostanejo_strani_cele(self):
        rezultat = strani.filter_pdf(self.vir, self.cilj, use_ocr=False, max_pages=50)
        self.assertEqual(len(rezultat.unreadable), 12)
        self.assertEqual(rezultat.ocr_pages, 0)


if __name__ == "__main__":
    unittest.main()
