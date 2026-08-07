import unittest
from datetime import date

from jedro.datumi import looks_like_range, parse_range


class ParseRange(unittest.TestCase):
    def test_pikčasti_razpon(self):
        self.assertEqual(parse_range("23.7.2026 - 29.7.2026"),
                         (date(2026, 7, 23), date(2026, 7, 29)))

    def test_letnica_samo_pri_drugem_datumu(self):
        self.assertEqual(parse_range("od 23. 7. do 29. 7. 2026"),
                         (date(2026, 7, 23), date(2026, 7, 29)))

    def test_pomisljaj(self):
        self.assertEqual(parse_range("19.07. – 04.08.2026"),
                         (date(2026, 7, 19), date(2026, 8, 4)))

    def test_en_sam_datum(self):
        self.assertEqual(parse_range("Letak od 22. 7. 2026"),
                         (date(2026, 7, 22), None))

    def test_ime_meseca(self):
        self.assertEqual(parse_range("Ferdo raziskuje svet Maj 2026"),
                         (date(2026, 5, 1), None))

    def test_razpon_cez_novo_leto(self):
        start, end = parse_range("28.12. - 3.1.2026")
        self.assertEqual((start, end), (date(2025, 12, 28), date(2026, 1, 3)))

    def test_brez_datumov(self):
        self.assertEqual(parse_range("Akcijski katalog"), (None, None))
        self.assertEqual(parse_range(None), (None, None))

    def test_neveljaven_datum(self):
        self.assertEqual(parse_range("32.13.2026"), (None, None))

    def test_prepozna_razpon(self):
        self.assertTrue(looks_like_range("od 1.8. do 7.8.2026"))
        self.assertFalse(looks_like_range("Katalog 30/26"))


if __name__ == "__main__":
    unittest.main()
