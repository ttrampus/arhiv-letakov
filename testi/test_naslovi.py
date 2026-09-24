import unittest

from jedro import naslovi


class Allowlist(unittest.TestCase):
    def test_sprejme_gostitelja_trgovine(self):
        self.assertTrue(naslovi.je_dovoljen("https://www.mercator.si/a.pdf", "mercator"))

    def test_sprejme_poddomeno(self):
        self.assertTrue(naslovi.je_dovoljen("https://letak.spar.si/x/getPdf.ashx", "spar"))

    def test_zavrne_tujo_domeno(self):
        self.assertFalse(naslovi.je_dovoljen("https://zlonamerni.si/a.pdf", "mercator"))

    def test_zavrne_domeno_druge_trgovine(self):
        self.assertFalse(naslovi.je_dovoljen("https://www.lidl.si/a.pdf", "mercator"))

    def test_zavrne_podobno_ime(self):
        # www.mercator.si.zlo.si ne sme prestati preverjanja pripone.
        self.assertFalse(naslovi.je_dovoljen("https://www.mercator.si.zlo.si/a.pdf", "mercator"))

    def test_zavrne_http(self):
        self.assertFalse(naslovi.je_dovoljen("http://www.mercator.si/a.pdf", "mercator"))

    def test_http_z_dovoljenjem(self):
        self.assertTrue(naslovi.je_dovoljen("http://www.mercator.si/a.pdf", "mercator",
                                            dovoli_http=True))

    def test_zavrne_druge_sheme(self):
        for url in ("file:///etc/passwd", "ftp://www.mercator.si/a", "gopher://x"):
            self.assertFalse(naslovi.je_dovoljen(url, "mercator"), url)

    def test_zavrne_poverilnice(self):
        self.assertFalse(naslovi.je_dovoljen("https://kdo:geslo@www.mercator.si/a", "mercator"))

    def test_zavrne_metadata_streznik(self):
        self.assertFalse(naslovi.je_dovoljen("https://169.254.169.254/latest/meta-data/", "lidl"))

    def test_zavrne_zasebne_naslove(self):
        for host in ("127.0.0.1", "10.1.2.3", "192.168.0.5", "172.16.0.1", "[::1]"):
            self.assertFalse(naslovi.je_dovoljen(f"https://{host}/a.pdf", "lidl"), host)

    def test_zavrne_javni_ip(self):
        self.assertFalse(naslovi.je_dovoljen("https://8.8.8.8/a.pdf", "lidl"))

    def test_zavrne_prazen(self):
        self.assertFalse(naslovi.je_dovoljen("", "lidl"))

    def test_neznana_trgovina_nima_dovoljenj(self):
        self.assertFalse(naslovi.je_dovoljen("https://www.mercator.si/a.pdf", "izmisljena"))

    def test_dodatni_gostitelj_iz_nastavitev(self):
        dodatni = {"mercator": ["nova.mercator-katalogi.si"]}
        self.assertTrue(naslovi.je_dovoljen("https://nova.mercator-katalogi.si/a.pdf",
                                            "mercator", dodatni=dodatni))

    def test_dodatni_gostitelj_za_vse_trgovine(self):
        dodatni = {"*": ["cdn.skupni.si"]}
        self.assertTrue(naslovi.je_dovoljen("https://cdn.skupni.si/a.pdf", "tus",
                                            dodatni=dodatni))

    def test_seznam_za_pozarni_zid_prestane_preverjanje(self):
        # Vsak gostitelj s seznama za požarni zid mora prestati preverjanje
        # vsaj ene trgovine, sicer bi seznama razhajala.
        for host in naslovi.ZA_POZARNI_ZID:
            self.assertTrue(any(naslovi.je_dovoljen(f"https://{host}/x", store)
                                for store in naslovi.DOVOLJENI), host)


class Maskiranje(unittest.TestCase):
    def test_geslo_izgine(self):
        skrit = naslovi.mask("http://sluzba:zelo-skrivno@proxy.podjetje.si:8080")
        self.assertNotIn("zelo-skrivno", skrit)
        self.assertNotIn("sluzba", skrit)
        self.assertIn("proxy.podjetje.si:8080", skrit)

    def test_brez_poverilnic_ostane_enak(self):
        self.assertEqual(naslovi.mask("http://proxy:8080"), "http://proxy:8080")

    def test_prazen(self):
        self.assertEqual(naslovi.mask(""), "")
        self.assertEqual(naslovi.mask(None), "")


if __name__ == "__main__":
    unittest.main()
