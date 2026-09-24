"""Prenos se mora ustaviti, preden velik ali napačen odgovor zasede strežnik."""

import http.server
import tempfile
import threading
import unittest
import unittest.mock
from pathlib import Path

from jedro import prenos
from jedro.modeli import Magazine
from jedro.nastavitve import Config
from jedro.povezava import Fetchers

from ._lokalno import dovoli_lokalni_streznik


class Streznik(http.server.BaseHTTPRequestHandler):
    """Streže toliko podatkov, kolikor jih odjemalec sprejme."""

    vsebina = b"%PDF-1.4\n" + b"x" * 4096
    ponovitve = 4000
    napovej_dolzino = False

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        if self.napovej_dolzino:
            self.send_header("Content-Length",
                             str(len(self.vsebina) * self.ponovitve))
        self.end_headers()
        try:
            for _ in range(self.ponovitve):
                self.wfile.write(self.vsebina)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


class Meje(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), Streznik)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.shutdown)
        self.vrata = self.httpd.server_address[1]

        dovoli_lokalni_streznik(self, self.vrata)

        self.cfg = Config(
            root=self.root, config_path=self.root / "nastavitve.yaml",
            archive_dir=self.root / "arhiv", meat_dir=self.root / "meso",
            db_path=self.root / "arhiv.db", log_dir=self.root / "dnevniki",
            delay_between_requests=0.0, max_pdf_mb=1, allow_http=True,
            # Testni strežnik teče na 127.0.0.1, zato ga moramo izrecno dovoliti.
            extra_hosts={"*": ["127.0.0.1"]})
        self.fetchers = Fetchers(self.cfg)
        self.addCleanup(self.fetchers.close)

    def naslov(self, pot="/letak.pdf"):
        return f"http://127.0.0.1:{self.vrata}{pot}"

    def prenesi(self):
        cilj = self.root / "letak.pdf"
        magazine = Magazine(store="test", title="Testni letak",
                            source_url=self.naslov("/"), file_url=self.naslov())
        return prenos.fetch_magazine(magazine, self.fetchers, cilj, store="test")

    def test_prevelik_prenos_se_ustavi(self):
        with self.assertRaises(prenos.DownloadError) as napaka:
            self.prenesi()
        self.assertIn("presegel", str(napaka.exception))

    def test_prevelik_prenos_ne_pusti_smeti(self):
        with self.assertRaises(prenos.DownloadError):
            self.prenesi()
        ostalo = list(self.root.glob("*.part")) + list(self.root.glob("letak.pdf"))
        self.assertEqual(ostalo, [])

    def test_napovedana_velikost_prepreci_prenos(self):
        Streznik.napovej_dolzino = True
        self.addCleanup(setattr, Streznik, "napovej_dolzino", False)
        with self.assertRaises(prenos.DownloadError) as napaka:
            self.prenesi()
        self.assertIn("napovedal", str(napaka.exception))

    def test_odgovor_ki_ni_pdf_se_zavrne(self):
        Streznik.vsebina = b"<html>napaka</html>"
        Streznik.ponovitve = 1
        self.addCleanup(setattr, Streznik, "vsebina", b"%PDF-1.4\n" + b"x" * 4096)
        self.addCleanup(setattr, Streznik, "ponovitve", 4000)
        with self.assertRaises(prenos.DownloadError) as napaka:
            self.prenesi()
        self.assertIn("ni PDF", str(napaka.exception))

    def test_tuj_gostitelj_se_ne_prenese(self):
        cilj = self.root / "letak.pdf"
        magazine = Magazine(store="test", title="Tuj", source_url="https://zlo.si/",
                            file_url="https://zlo.si/a.pdf")
        with self.assertRaises(Exception):
            prenos.fetch_magazine(magazine, self.fetchers, cilj, store="test")


if __name__ == "__main__":
    unittest.main()
