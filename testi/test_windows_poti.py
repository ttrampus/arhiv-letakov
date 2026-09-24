"""Poti, ki veljajo samo, kadar program teče kot .exe ali piše na delnico."""

import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path, PureWindowsPath

from jedro import nastavitve
from jedro.nastavitve import Config, je_omrezna_pot


class OmrezneMape(unittest.TestCase):
    def test_unc_pot_je_prepoznana(self):
        self.assertTrue(je_omrezna_pot(PureWindowsPath(r"\\dms01\letaki\arhiv")))

    def test_krajevna_pot_ni_omrezna(self):
        self.assertFalse(je_omrezna_pot(Path("/var/lib/arhiv-letakov")))

    def nastavitve(self, **kwargs) -> Config:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        privzeto = dict(root=root, config_path=root / "n.yaml",
                        archive_dir=root / "a", meat_dir=root / "m",
                        db_path=root / "b.db", log_dir=root / "d")
        privzeto.update(kwargs)
        return Config(**privzeto)

    def test_baza_na_delnici_opozori(self):
        cfg = self.nastavitve(db_path=PureWindowsPath(r"\\dms01\letaki\arhiv.db"))
        self.assertTrue(any("SQLite" in o for o in cfg.opozorila()))

    def test_dnevniki_na_delnici_opozorijo(self):
        cfg = self.nastavitve(log_dir=PureWindowsPath(r"\\dms01\letaki\dnevniki"))
        self.assertTrue(any("dnevnik" in o for o in cfg.opozorila()))

    def test_krajevne_poti_ne_opozorijo(self):
        self.assertEqual(self.nastavitve().opozorila(), [])


class BranjeNastavitev(unittest.TestCase):
    def test_unc_arhiv_ostane_nedotaknjen(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        pot = Path(temp.name) / "nastavitve.yaml"
        # V enojnih narekovajih YAML pusti poševnice pri miru.
        pot.write_text(r"mapa_arhiva: '\\dms01\letaki\arhiv'" + "\n", encoding="utf-8")
        cfg = nastavitve.load(pot)
        self.assertTrue(str(cfg.archive_dir).startswith(r"\\dms01"))

    def test_zapakiran_program_isce_nastavitve_ob_sebi(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        program = Path(temp.name).resolve() / "arhiv-letakov.exe"
        with unittest.mock.patch.object(nastavitve, "je_zapakiran", return_value=True):
            with unittest.mock.patch.object(nastavitve.sys, "executable", str(program)):
                with unittest.mock.patch.dict(os.environ, {"PROGRAMDATA": temp.name + "x"}):
                    self.assertEqual(nastavitve.domaca_mapa(), program.parent)

    def test_zapakiran_program_prednost_programdata(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        skupna = Path(temp.name) / "arhiv-letakov"
        skupna.mkdir()
        (skupna / "nastavitve.yaml").write_text("", encoding="utf-8")
        with unittest.mock.patch.object(nastavitve, "je_zapakiran", return_value=True):
            with unittest.mock.patch.dict(os.environ, {"PROGRAMDATA": temp.name}):
                self.assertEqual(nastavitve.domaca_mapa(), skupna)

    def test_nezapakiran_program_uporabi_koren_projekta(self):
        self.assertTrue((nastavitve.domaca_mapa() / "letaki.py").exists())


if __name__ == "__main__":
    unittest.main()
