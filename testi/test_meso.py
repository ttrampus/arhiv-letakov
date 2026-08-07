import unittest

from jedro.meso import find_meat, fold, page_has_meat


class Poravnava(unittest.TestCase):
    def test_sumniki_odpadejo(self):
        self.assertEqual(fold("Piščančji"), "piscancji")
        self.assertEqual(fold("ĆEVAPČIČI"), "cevapcici")

    def test_precrtana_crka_ni_razstavljiva(self):
        self.assertEqual(fold("Đuveč"), "duvec")


class Iskanje(unittest.TestCase):
    def test_najde_vrsto(self):
        self.assertTrue(page_has_meat("Svinjska ribica 7,99 EUR")[0])

    def test_najde_kljub_ocr_brez_sumnikov(self):
        self.assertTrue(page_has_meat("PISCANCJE PRSA 1 kg")[0])

    def test_najde_izdelek(self):
        self.assertTrue(page_has_meat("Kranjska klobasa, 2 kos")[0])

    def test_najde_proizvajalca(self):
        self.assertTrue(page_has_meat("Argeta pašteta 95 g")[0])

    def test_mesto_in_mesec_nista_meso(self):
        self.assertFalse(page_has_meat("Akcija velja v mesecu avgustu v mestu Celje")[0])

    def test_police_niso_meso(self):
        self.assertFalse(page_has_meat("Izdelki na policah trgovine")[0])

    def test_kokos_ni_perutnina(self):
        self.assertFalse(page_has_meat("Kokosovo mleko 400 ml")[0])
        self.assertTrue(page_has_meat("Kokosje bedro sveže")[0])

    def test_ribe_ne_stejejo(self):
        self.assertFalse(page_has_meat("Losos file in tuna v olju")[0])

    def test_prazna_stran(self):
        self.assertEqual(find_meat(""), [])

    def test_zadetki_so_cele_besede(self):
        self.assertIn("klobase", find_meat("Domače klobase v akciji"))


if __name__ == "__main__":
    unittest.main()
