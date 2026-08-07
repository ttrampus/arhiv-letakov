import unittest
from datetime import date

from jedro.izbor import is_weekly_food_flyer, validity_days
from jedro.modeli import Magazine


def letak(title, date_from=None, date_to=None):
    return Magazine(store="test", title=title, source_url="", date_from=date_from,
                    date_to=date_to)


class Izbor(unittest.TestCase):
    def test_tematski_naslov_pade(self):
        keep, reason = is_weekly_food_flyer(letak("Katalog Šola 2026"))
        self.assertFalse(keep)
        self.assertIn("šola", reason)

    def test_tematski_naslov_pade_tudi_brez_sumnikov(self):
        keep, _ = is_weekly_food_flyer(letak("Katalog Sola 2026"))
        self.assertFalse(keep)

    def test_zavrnitev_pred_sprejetjem(self):
        keep, _ = is_weekly_food_flyer(letak("Lidlov katalog vinski teden"))
        self.assertFalse(keep)

    def test_sprejeta_beseda_obvelja_brez_datumov(self):
        keep, reason = is_weekly_food_flyer(letak("Letak od 22. 7. 2026"))
        self.assertTrue(keep)
        self.assertEqual(reason, "naslov tedenskega letaka")

    def test_tedenska_ostevilcenost(self):
        keep, reason = is_weekly_food_flyer(letak("Katalog 30/26"))
        self.assertTrue(keep)
        self.assertEqual(reason, "tedenska oštevilčenost")

    def test_kratka_veljavnost_obvelja(self):
        keep, _ = is_weekly_food_flyer(
            letak("Nekaj novega", date(2026, 8, 1), date(2026, 8, 7)))
        self.assertTrue(keep)

    def test_dolga_veljavnost_pade(self):
        keep, reason = is_weekly_food_flyer(
            letak("Nekaj novega", date(2026, 1, 1), date(2026, 12, 31)))
        self.assertFalse(keep)
        self.assertIn("364", reason)

    def test_meja_je_nastavljiva(self):
        magazine = letak("Nekaj novega", date(2026, 8, 1), date(2026, 8, 31))
        self.assertTrue(is_weekly_food_flyer(magazine, max_days=40)[0])
        self.assertFalse(is_weekly_food_flyer(magazine, max_days=10)[0])

    def test_brez_datumov_in_besed_obdrzimo(self):
        keep, _ = is_weekly_food_flyer(letak("Nekaj novega"))
        self.assertTrue(keep)

    def test_lastna_seznama(self):
        self.assertFalse(is_weekly_food_flyer(letak("Redni katalog"), deny=["redni"])[0])
        self.assertTrue(is_weekly_food_flyer(letak("Katalog Šola"), deny=[], allow=["šola"])[0])

    def test_dolzina_veljavnosti(self):
        self.assertEqual(
            validity_days(letak("x", date(2026, 8, 1), date(2026, 8, 8))), 7)
        self.assertIsNone(validity_days(letak("x", date(2026, 8, 1))))


if __name__ == "__main__":
    unittest.main()
