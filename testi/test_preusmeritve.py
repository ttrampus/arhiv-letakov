"""Preusmeritev ne sme odpeljati programa z dovoljenega gostitelja."""

import http.server
import tempfile
import threading
import unittest
import unittest.mock
from pathlib import Path

import requests

from jedro.naslovi import ZavrnjenNaslov
from jedro.nastavitve import Config
from jedro.povezava import Fetchers

from ._lokalno import dovoli_lokalni_streznik

CILJ = "https://zlonamerni.si/prevzem"


class Streznik(http.server.BaseHTTPRequestHandler):
    kam = CILJ
    skoki = 0

    def do_GET(self):
        if self.path.startswith("/krog"):
            # Neskončno preusmerjanje na samega sebe.
            self.send_response(302)
            self.send_header("Location", "/krog")
            self.end_headers()
            return
        self.send_response(302)
        self.send_header("Location", self.kam)
        self.end_headers()

    def log_message(self, *args):
        pass


class Preusmeritve(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), Streznik)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.shutdown)
        vrata = self.httpd.server_address[1]
        dovoli_lokalni_streznik(self, vrata)
        self.naslov = f"http://127.0.0.1:{vrata}/letak"

        cfg = Config(root=root, config_path=root / "n.yaml", archive_dir=root / "a",
                     meat_dir=root / "m", db_path=root / "b.db", log_dir=root / "d",
                     delay_between_requests=0.0, allow_http=True,
                     extra_hosts={"*": ["127.0.0.1"]})
        self.fetchers = Fetchers(cfg)
        self.addCleanup(self.fetchers.close)

    def test_preusmeritev_na_tujo_domeno_se_zavrne(self):
        with self.assertRaises(ZavrnjenNaslov):
            self.fetchers.http.get(self.naslov, store="test")

    def test_preusmeritev_na_metadata_se_zavrne(self):
        Streznik.kam = "http://169.254.169.254/latest/meta-data/"
        self.addCleanup(setattr, Streznik, "kam", CILJ)
        with self.assertRaises(ZavrnjenNaslov):
            self.fetchers.http.get(self.naslov, store="test")

    def test_krozna_preusmeritev_se_ustavi(self):
        with self.assertRaises(requests.TooManyRedirects):
            self.fetchers.http.get(f"{self.naslov.replace('/letak', '/krog')}",
                                   store="test")


if __name__ == "__main__":
    unittest.main()
