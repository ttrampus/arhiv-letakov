import tempfile
import unittest
from pathlib import Path

from jedro.zaklep import Zaklep, Zaseden


class Zaklepanje(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "arhiv.db.lock"

    def test_drugi_zagon_ne_pride_zraven(self):
        with Zaklep(self.path):
            with self.assertRaises(Zaseden):
                with Zaklep(self.path):
                    self.fail("dva zagona hkrati")

    def test_po_koncu_je_spet_prost(self):
        with Zaklep(self.path):
            pass
        with Zaklep(self.path):
            pass
        self.assertFalse(self.path.exists())

    def test_sprosti_se_tudi_ob_napaki(self):
        with self.assertRaises(RuntimeError):
            with Zaklep(self.path):
                raise RuntimeError("zajem se je sesul")
        with Zaklep(self.path):
            pass

    def test_zapise_pid(self):
        import os
        with Zaklep(self.path):
            self.assertEqual(self.path.read_text(encoding="utf-8"), str(os.getpid()))

    def test_naredi_mapo(self):
        globlje = Path(self.temp.name) / "nova" / "arhiv.db.lock"
        with Zaklep(globlje):
            self.assertTrue(globlje.exists())


if __name__ == "__main__":
    unittest.main()
