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
        self.assertEqual(cfg.archive_dir, Path(self.temp.name) / "katalogi")

    def test_absolutna_pot_ostane(self):
        cfg = self.nalozi("mapa_arhiva: /srv/letaki\n")
        self.assertEqual(cfg.archive_dir, Path("/srv/letaki"))

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

    def test_peskovnik_privzeto_vklopljen(self):
        self.assertFalse(self.nalozi("").browser_no_sandbox)

    def test_peskovnik_izklopi_okolje(self):
        with unittest.mock.patch.dict(os.environ, {"ARHIV_BREZ_PESKOVNIKA": "1"}):
            self.assertTrue(self.nalozi("").browser_no_sandbox)

    def test_zaklep_ob_bazi(self):
        cfg = self.nalozi("baza: /srv/letaki/arhiv.db\n")
        self.assertEqual(cfg.lock_path, Path("/srv/letaki/arhiv.db.lock"))

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
