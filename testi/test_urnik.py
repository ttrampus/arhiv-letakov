import unittest

from jedro.urnik import describe, is_manual, to_oncalendar


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

    def test_opis(self):
        self.assertEqual(describe("pon,cet 06:15"), "Mon,Thu 06:15:00")


if __name__ == "__main__":
    unittest.main()
