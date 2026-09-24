"""Zaščite v jedro/povezava.py, preverjene z resničnimi povezavami na lokalne strežnike."""

import http.server
import socketserver
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

from jedro import naslovi
from jedro.nastavitve import Config
from jedro.povezava import Fetchers, NapakaPosrednika, OmejitevPresezena

from ._lokalno import dovoli_lokalni_streznik


class _Streznik(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def zazeni(test, handler):
    httpd = _Streznik(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    test.addCleanup(httpd.server_close)
    test.addCleanup(httpd.shutdown)
    return httpd.server_address[1]


def nastavitve(test, **kwargs) -> Config:
    temp = tempfile.TemporaryDirectory()
    test.addCleanup(temp.cleanup)
    root = Path(temp.name)
    privzeto = dict(root=root, config_path=root / "n.yaml", archive_dir=root / "a",
                    meat_dir=root / "m", db_path=root / "b.db", log_dir=root / "d",
                    delay_between_requests=0.0, max_retries=0, allow_http=True,
                    extra_hosts={"*": ["127.0.0.1"]})
    privzeto.update(kwargs)
    return Config(**privzeto)


class Tiho(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass


class NaslovPovezave(unittest.TestCase):
    """Ime prestane seznam, povezava pa pristane na notranjem naslovu."""

    def test_notranji_naslov_se_zavrne_ob_povezavi(self):
        class Odgovor(Tiho):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"notranje")

        vrata = zazeni(self, Odgovor)
        # Preverjanje imena izklopimo, preverjanja naslova povezave pa ne:
        # to je položaj, ko DNS dovoljeno ime usmeri na notranji naslov.
        for zaplata in (unittest.mock.patch("jedro.naslovi.je_ip", return_value=False),
                        unittest.mock.patch("jedro.naslovi._je_zaseben_ip", return_value=False),
                        unittest.mock.patch.dict("jedro.naslovi._PRIVZETA_VRATA", {"http": vrata})):
            zaplata.start()
            self.addCleanup(zaplata.stop)
        fetchers = Fetchers(nastavitve(self))
        self.addCleanup(fetchers.close)
        with self.assertRaises(naslovi.ZavrnjenNaslov) as napaka:
            fetchers.http.get(f"http://127.0.0.1:{vrata}/", store="test")
        self.assertIn("ni javen", str(napaka.exception))


class OmejenoBranje(unittest.TestCase):
    def pripravi(self, handler, **kwargs):
        vrata = zazeni(self, handler)
        dovoli_lokalni_streznik(self, vrata)
        fetchers = Fetchers(nastavitve(self, **kwargs))
        self.addCleanup(fetchers.close)
        return fetchers, f"http://127.0.0.1:{vrata}/"

    def test_prevelika_stran_se_ne_nalozi_v_pomnilnik(self):
        class Velika(Tiho):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                try:
                    for _ in range(3000):
                        self.wfile.write(b"x" * 1024)
                except OSError:
                    pass

        fetchers, naslov = self.pripravi(Velika, max_page_mb=1)
        with self.assertRaises(OmejitevPresezena):
            fetchers.http.get(naslov, store="test")

    def test_pocasen_streznik_ne_drzi_prenosa(self):
        class Kapljanje(Tiho):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b"x" * 70000)
                        self.wfile.flush()
                        time.sleep(0.2)
                except OSError:
                    pass

        fetchers, naslov = self.pripravi(Kapljanje, request_timeout=1)
        zacetek = time.monotonic()
        with self.assertRaises(OmejitevPresezena):
            fetchers.http.get(naslov, store="test")
        self.assertLess(time.monotonic() - zacetek, 10)

    def test_prijava_ne_gre_na_drug_gostitelj(self):
        prejete = {}

        class Cilj(Tiho):
            def do_GET(self):
                prejete["authorization"] = self.headers.get("Authorization")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

        vrata_cilja = zazeni(self, Cilj)

        class Preusmeritev(Tiho):
            def do_GET(self):
                self.send_response(302)
                # localhost je drug gostitelj kot 127.0.0.1, a isti stroj.
                self.send_header("Location", f"http://localhost.test:{vrata_cilja}/")
                self.end_headers()

        vrata = zazeni(self, Preusmeritev)
        dovoli_lokalni_streznik(self, vrata)
        # Oba gostitelja vodita na isti lokalni stroj.
        prava = __import__("socket").getaddrinfo

        def razresi(host, *args, **kwargs):
            return prava("127.0.0.1" if host == "localhost.test" else host, *args, **kwargs)

        zaplata = unittest.mock.patch("socket.getaddrinfo", side_effect=razresi)
        zaplata.start()
        self.addCleanup(zaplata.stop)
        cfg = nastavitve(self, extra_hosts={"*": ["127.0.0.1", "localhost.test"]})
        fetchers = Fetchers(cfg)
        self.addCleanup(fetchers.close)
        with unittest.mock.patch.dict("jedro.naslovi._PRIVZETA_VRATA", {"http": None}):
            # Brez preverjanja vrat, ker lokalna strežnika tečeta na različnih.
            with unittest.mock.patch("jedro.naslovi.preveri",
                                     side_effect=lambda url, *a, **k: url):
                fetchers.http.get(f"http://127.0.0.1:{vrata}/", store="test",
                                  headers={"Authorization": "Bearer skrivno"})
        self.assertIsNone(prejete["authorization"])


class Posrednik(unittest.TestCase):
    def test_posrednik_iz_nastavitev_se_uporabi(self):
        videno = []

        class Proxy(Tiho):
            def do_GET(self):
                videno.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"skozi posrednika")

        vrata = zazeni(self, Proxy)
        cfg = nastavitve(self, proxy=f"http://127.0.0.1:{vrata}",
                         extra_hosts={"*": ["www.primer.si"]})
        fetchers = Fetchers(cfg)
        self.addCleanup(fetchers.close)
        odgovor = fetchers.http.get("http://www.primer.si/letak", store="test")
        self.assertEqual(odgovor.text, "skozi posrednika")
        self.assertEqual(videno, ["http://www.primer.si/letak"])

    def test_posrednik_iz_nastavitev_prevlada_nad_okoljem(self):
        videno = []

        class Proxy(Tiho):
            def do_GET(self):
                videno.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

        vrata = zazeni(self, Proxy)
        cfg = nastavitve(self, proxy=f"http://127.0.0.1:{vrata}",
                         extra_hosts={"*": ["www.primer.si"]})
        with unittest.mock.patch.dict("os.environ", {"HTTP_PROXY": "http://127.0.0.1:9",
                                                     "HTTPS_PROXY": "http://127.0.0.1:9"}):
            fetchers = Fetchers(cfg)
            self.addCleanup(fetchers.close)
            fetchers.http.get("http://www.primer.si/", store="test")
        self.assertEqual(len(videno), 1)

    def test_407_da_jasno_sporocilo(self):
        class Zahteva(Tiho):
            def do_CONNECT(self):
                self.send_response(407)
                self.send_header("Proxy-Authenticate", "Negotiate")
                self.send_header("Content-Length", "0")
                self.end_headers()

        vrata = zazeni(self, Zahteva)
        cfg = nastavitve(self, proxy=f"http://127.0.0.1:{vrata}",
                         extra_hosts={"*": ["www.primer.si"]})
        fetchers = Fetchers(cfg)
        self.addCleanup(fetchers.close)
        with self.assertRaises(NapakaPosrednika) as napaka:
            fetchers.http.get("https://www.primer.si/", store="test")
        self.assertIn("407", str(napaka.exception))


if __name__ == "__main__":
    unittest.main()
