import unittest
from pathlib import Path

from jedro.urnik import describe, is_manual, to_cron, to_oncalendar


class Urnik(unittest.TestCase):
    def test_dnevno(self):
        self.assertEqual(to_oncalendar("dnevno 06:00"), ["*-*-* 06:00:00"])

    def test_dnevno_dvakrat(self):
        self.assertEqual(to_oncalendar("dnevno 06:00,18:30"),
                         ["*-*-* 06:00:00", "*-*-* 18:30:00"])

    def test_tedensko_je_cetrtek(self):
        self.assertEqual(to_oncalendar("tedensko"), ["Thu 06:00:00"])

    def test_izbrani_dnevi(self):
        self.assertEqual(to_oncalendar("pon,cet 06:15"), ["Mon,Thu 06:15:00"])

    def test_dan_s_sumnikom(self):
        self.assertEqual(to_oncalendar("čet 07:00"), ["Thu 07:00:00"])

    def test_ura_z_eno_stevilko(self):
        self.assertEqual(to_oncalendar("dnevno 6:05"), ["*-*-* 06:05:00"])

    def test_brez_ure_privzeto_sest(self):
        self.assertEqual(to_oncalendar("dnevno"), ["*-*-* 06:00:00"])

    def test_neznan_dan_pade_na_vsak_dan(self):
        self.assertEqual(to_oncalendar("nekaj 06:00"), ["*-*-* 06:00:00"])

    def test_rocno(self):
        for value in ("ročno", "rocno", "nikoli", "brez", " Ročno "):
            self.assertTrue(is_manual(value), value)
        self.assertFalse(is_manual("dnevno 06:00"))

    def test_cron_dnevno(self):
        self.assertEqual(to_cron("dnevno 06:00"), ["0 6 * * *"])

    def test_cron_tedensko_je_cetrtek(self):
        self.assertEqual(to_cron("tedensko"), ["0 6 * * 4"])

    def test_cron_izbrani_dnevi(self):
        self.assertEqual(to_cron("pon,cet 06:15"), ["15 6 * * 1,4"])

    def test_cron_nedelja_je_nic(self):
        self.assertEqual(to_cron("ned 08:00"), ["0 8 * * 0"])

    def test_cron_dvakrat_na_dan(self):
        self.assertEqual(to_cron("dnevno 06:00,18:30"), ["0 6 * * *", "30 18 * * *"])

    def test_cron_brez_vodilnih_nicel(self):
        # cron ne mara "06"; ura in minuta gresta noter kot števili.
        self.assertEqual(to_cron("dnevno 6:05"), ["5 6 * * *"])

    def test_opis(self):
        self.assertEqual(describe("pon,cet 06:15"), "Mon,Thu 06:15:00")


if __name__ == "__main__":
    unittest.main()


class WindowsOpravilo(unittest.TestCase):
    """Windows del preverimo neposredno; na Linuxu se sicer ne naloži."""

    def setUp(self):
        from jedro.urnik import _windows
        self.win = _windows

    def test_dnevni_urnik(self):
        self.assertEqual(self.win.sprozilci("dnevno 06:00"),
                         [{"dnevi": [], "ura": "06:00"}])

    def test_tedenski_urnik(self):
        self.assertEqual(self.win.sprozilci("cet 06:15"),
                         [{"dnevi": ["Thursday"], "ura": "06:15"}])

    def test_vec_ur_da_vec_sprozilcev(self):
        self.assertEqual(len(self.win.sprozilci("dnevno 06:00, 18:00")), 2)

    def test_vec_dni(self):
        self.assertEqual(self.win.sprozilci("pon,cet 07:00"),
                         [{"dnevi": ["Monday", "Thursday"], "ura": "07:00"}])

    def test_ukaz_vedno_poda_nastavitve(self):
        koren = Path(r"C:\arhiv-letakov")
        _, argumenti = self.win.ukaz_programa(koren, koren / "nastavitve.yaml")
        self.assertIn("--nastavitve", argumenti)
        self.assertTrue(argumenti.endswith("prenesi"))

    def test_namestitev_napoti_na_skripto(self):
        with self.assertRaises(RuntimeError) as napaka:
            self.win.install(Path("."), "dnevno 06:00")
        self.assertIn("namesti-windows.ps1", str(napaka.exception))
