import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from jedro import nastavitve


class Branje(unittest.TestCase):
    def nalozi(self, besedilo):
        directory = Path(self.temp.name)
        path = directory / "nastavitve.yaml"
        path.write_text(besedilo, encoding="utf-8")
        return nastavitve.load(path)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_privzete_vrednosti(self):
        cfg = self.nalozi("")
        self.assertEqual(cfg.archive_dir.name, "arhiv")
        self.assertEqual(cfg.meat_dir.name, "arhiv-meso")
        self.assertEqual(cfg.schedule, "dnevno 06:00")
        self.assertEqual(cfg.delay_between_requests, 2.0)
        self.assertTrue(cfg.meat_enabled)
        self.assertEqual(cfg.notify_after, 3)

    def test_relativne_poti_glede_na_datoteko(self):
        cfg = self.nalozi("mapa_arhiva: katalogi\n")
        # resolve(): na Windows je %TEMP% lahko v kratki obliki (RUNNER~1).
        self.assertEqual(cfg.archive_dir, Path(self.temp.name).resolve() / "katalogi")

    def test_absolutna_pot_ostane(self):
        # Absolutna pot za sistem, na katerem test teče (C:\... ali /...).
        absolutna = Path(self.temp.name).resolve() / "letaki"
        cfg = self.nalozi(f"mapa_arhiva: '{absolutna}'\n")
        self.assertEqual(cfg.archive_dir, absolutna)

    def test_posrednik_iz_nastavitev(self):
        cfg = self.nalozi("omrezje:\n  posrednik: http://proxy.podjetje.si:3128\n")
        self.assertEqual(cfg.proxy, "http://proxy.podjetje.si:3128")

    def test_posrednik_iz_okolja(self):
        with unittest.mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://p:3128"}):
            self.assertEqual(self.nalozi("").proxy, "http://p:3128")

    def test_nastavitve_prevladajo_nad_okoljem(self):
        with unittest.mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://okolje:3128"}):
            cfg = self.nalozi("omrezje:\n  posrednik: http://iz-datoteke:3128\n")
        self.assertEqual(cfg.proxy, "http://iz-datoteke:3128")

    def test_posrednik_v_izpisu_nima_gesla(self):
        cfg = self.nalozi("omrezje:\n  posrednik: http://sluzba:skrivnost@proxy:3128\n")
        self.assertNotIn("skrivnost", cfg.proxy_za_izpis)
        self.assertIn("proxy:3128", cfg.proxy_za_izpis)

    def test_privzete_meje(self):
        cfg = self.nalozi("")
        self.assertEqual(cfg.max_pdf_mb, 150)
        self.assertEqual(cfg.max_pages, 300)

    def test_meje_iz_nastavitev(self):
        cfg = self.nalozi("meje:\n  najvecji_pdf_mb: 40\n  najvec_strani: 80\n")
        self.assertEqual(cfg.max_pdf_mb, 40)
        self.assertEqual(cfg.max_pages, 80)

    def test_dodatni_gostitelji(self):
        cfg = self.nalozi("omrezje:\n  dovoljeni_gostitelji:\n    spar: [nov.spar.si]\n")
        self.assertEqual(cfg.extra_hosts, {"spar": ["nov.spar.si"]})

    def test_zaklep_ob_bazi(self):
        baza = Path(self.temp.name).resolve() / "letaki" / "arhiv.db"
        cfg = self.nalozi(f"baza: '{baza}'\n")
        self.assertEqual(cfg.lock_path, baza.with_name("arhiv.db.lock"))

    def test_bom_iz_powershell(self):
        # Windows PowerShell 5.1 zapiše UTF-8 z BOM; nastavitve morajo delovati.
        pot = Path(self.temp.name) / "nastavitve.yaml"
        pot.write_bytes(b"\xef\xbb\xbfurnik: cet 06:00\n")
        self.assertEqual(nastavitve.load(pot).schedule, "cet 06:00")

    def test_nicelna_meja_se_zavrne(self):
        with self.assertRaises(nastavitve.NapacneNastavitve):
            self.nalozi("meje:\n  najvecji_pdf_mb: 0\n")

    def test_trgovine(self):
        cfg = self.nalozi("trgovine:\n  spar:\n    vklopljeno: false\n")
        self.assertFalse(cfg.store_enabled("spar"))
        self.assertTrue(cfg.store_enabled("lidl"))

    def test_izbor_in_obvescanje(self):
        cfg = self.nalozi(
            "izbor:\n  samo_zivila: false\n  najvec_dni_veljavnosti: 40\n"
            "  zavrni_besede: [vino]\n"
            "obvescanje:\n  po_neuspehih: 5\n  webhook: https://primer\n")
        self.assertFalse(cfg.only_food)
        self.assertEqual(cfg.max_validity_days, 40)
        self.assertEqual(cfg.deny_keywords, ["vino"])
        self.assertEqual(cfg.notify_after, 5)
        self.assertEqual(cfg.notify_webhook, "https://primer")
