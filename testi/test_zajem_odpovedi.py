"""Zajem mora okvare pokazati: izhodna koda, stanje trgovine, obvestilo."""

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from pypdf import PdfWriter

import letaki
from jedro import strani
from jedro.baza import Archive
from jedro.modeli import Magazine
from jedro.nastavitve import Config


def nastavitve(root: Path, **kwargs) -> Config:
    privzeto = dict(root=root, config_path=root / "n.yaml", archive_dir=root / "arhiv",
                    meat_dir=root / "meso", db_path=root / "arhiv.db", log_dir=root / "d",
                    delay_between_requests=0.0, meat_enabled=False, notify_after=1,
                    only_food=False)
    privzeto.update(kwargs)
    return Config(**privzeto)


class Argumenti:
    stores = ["lazna"]
    dry_run = False
    all = False
    no_meat = True


class LaznaTrgovina:
    """Najde en letak, katerega povezavo je preverjanje zavrnilo."""
    name = "lazna"
    label = "Lažna"

    def find_magazines(self, fetchers):
        return [Magazine(store="lazna", title="Akcijski katalog", source_url="https://x.si",
                         file_url="")]


class Zapisljivost(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_nedosegljiv_arhiv_se_javi(self):
        # Mapa pod datoteko: tja ni mogoče pisati na nobenem sistemu.
        (self.root / "datoteka").write_text("x")
        cfg = nastavitve(self.root, archive_dir=self.root / "datoteka" / "arhiv")
        self.assertIsNotNone(letaki._preveri_zapisljivost(cfg))

    def test_zapisljiv_arhiv_je_v_redu(self):
        self.assertIsNone(letaki._preveri_zapisljivost(nastavitve(self.root)))

    def test_nedosegljiv_arhiv_ustavi_zajem_z_napako_in_obvestilom(self):
        (self.root / "datoteka").write_text("x")
        cfg = nastavitve(self.root, archive_dir=self.root / "datoteka" / "arhiv")
        with unittest.mock.patch("jedro.obvestila.send") as poslji:
            self.assertEqual(letaki._run(Argumenti(), cfg), 1)
        poslji.assert_called_once()


class TihaOdpoved(unittest.TestCase):
    def test_zavrnjeni_prenosi_stejejo_kot_okvara_trgovine(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = nastavitve(Path(temp))
            with unittest.mock.patch("letaki.get_stores", return_value=[LaznaTrgovina()]), \
                    unittest.mock.patch("jedro.obvestila.send") as poslji:
                izid = letaki._run(Argumenti(), cfg)
            self.assertEqual(izid, 1)
            poslji.assert_called_once()
            with Archive(cfg.db_path) as archive:
                self.assertEqual(archive.failing_stores(1)[0]["store"], "lazna")


class IzoliranaObdelava(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vir = Path(self.temp.name) / "letak.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=200, height=200)
        with self.vir.open("wb") as handle:
            writer.write(handle)
        self.cilj = Path(self.temp.name) / "meso" / "letak.pdf"

    def test_rezultat_pride_iz_otroka(self):
        rezultat = strani.filter_pdf_izolirano(self.vir, self.cilj, use_ocr=False,
                                               trdi_rok_s=60, pomnilnik_mb=2048)
        self.assertEqual(rezultat.total, 3)
        self.assertTrue(self.cilj.exists())

    def test_trdi_rok_ubije_obdelavo(self):
        with self.assertRaises(strani.CasPotekel):
            strani.filter_pdf_izolirano(self.vir, self.cilj, use_ocr=False,
                                        trdi_rok_s=0.001)
        self.assertFalse(self.cilj.with_suffix(".pdf.part").exists())

    def test_ubit_otrok_ne_pusti_zacasnih_map(self):
        import glob
        import os
        vzorec = os.path.join(tempfile.gettempdir(), "arhiv-letakov-pdf-*")
        pred = set(glob.glob(vzorec))
        with self.assertRaises(strani.CasPotekel):
            strani.filter_pdf_izolirano(self.vir, self.cilj, use_ocr=False, trdi_rok_s=0.001)
        strani.filter_pdf_izolirano(self.vir, self.cilj, use_ocr=False, trdi_rok_s=60)
        self.assertEqual(set(glob.glob(vzorec)), pred)

    def test_prevelik_pdf_ostane_prepoznaven(self):
        with self.assertRaises(strani.PrevelikPdf):
            strani.filter_pdf_izolirano(self.vir, self.cilj, use_ocr=False,
                                        max_pages=1, trdi_rok_s=60)

    def test_pokvarjen_pdf_ne_podre_klicatelja(self):
        self.vir.write_bytes(b"%PDF-1.4\n" + b"\x00" * 100)
        with self.assertRaises(RuntimeError):
            strani.filter_pdf_izolirano(self.vir, self.cilj, use_ocr=False, trdi_rok_s=60)


if __name__ == "__main__":
    unittest.main()


def _zasedi(meja_mb: int, zasedba_mb: int) -> None:
    """V otroku: postavi mejo in poskusi zasesti več. Izhod 0 = meja je zdržala."""
    import sys
    strani._omeji_pomnilnik(meja_mb)
    try:
        podatki = bytearray(zasedba_mb * 1024 * 1024)
        podatki[-1] = 1
    except MemoryError:
        sys.exit(0)
    sys.exit(3)


def _je_wine() -> bool:
    import os
    if os.name != "nt":
        return False
    import ctypes
    return hasattr(ctypes.WinDLL("ntdll"), "wine_get_version")


class MejaPomnilnika(unittest.TestCase):
    def test_otrok_ne_more_cez_mejo(self):
        if _je_wine():
            # Wine Job Object ustvari, a meje pomnilnika ne izvaja; test ima
            # pomen samo na pravem Windows (posel windows v CI).
            self.skipTest("Wine ne izvaja meje pomnilnika v Job Object")
        import multiprocessing
        proces = multiprocessing.get_context("spawn").Process(target=_zasedi, args=(300, 600))
        proces.start()
        proces.join(60)
        self.assertEqual(proces.exitcode, 0, "otrok je zasedel več pomnilnika, kot dovoli meja")

    def test_pod_mejo_gre(self):
        import multiprocessing
        proces = multiprocessing.get_context("spawn").Process(target=_zasedi, args=(600, 50))
        proces.start()
        proces.join(60)
        self.assertEqual(proces.exitcode, 3)


@unittest.skipIf(__import__("os").name == "nt", "skupine procesov so POSIX")
class VnukiInPomnilnik(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        self.vir = self.root / "letak.pdf"
        with self.vir.open("wb") as handle:
            writer.write(handle)

    def test_uboj_pobere_tudi_zataknjen_pdftoppm(self):
        import os
        import stat
        import time
        # Lažna pdftoppm in tesseract: prvi zapiše svoj PID in obvisi.
        bin_ = self.root / "bin"
        bin_.mkdir()
        pid_datoteka = self.root / "pid"
        for ime, vsebina in (("pdftoppm", f"#!/bin/sh\necho $$ > {pid_datoteka}\nexec sleep 300\n"),
                             ("tesseract", "#!/bin/sh\nexit 0\n")):
            pot = bin_ / ime
            pot.write_text(vsebina)
            pot.chmod(pot.stat().st_mode | stat.S_IEXEC)
        with unittest.mock.patch.dict(os.environ, {"PATH": f"{bin_}:{os.environ['PATH']}"}):
            with self.assertRaises(strani.CasPotekel):
                strani.filter_pdf_izolirano(self.vir, self.root / "m.pdf", use_ocr=True,
                                            trdi_rok_s=8, page_timeout_s=300)
        pid = int(pid_datoteka.read_text())
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(pid, 9)
            self.fail("zataknjen pdftoppm je preživel uboj otroka")



@unittest.skipUnless(__import__("os").name == "nt", "Job Object je Windows")
class VnukiWindows(unittest.TestCase):
    def test_uboj_pobere_tudi_zataknjen_pdftoppm(self):
        import ctypes
        import os
        import sys
        import time
        from ctypes import wintypes

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            vir = root / "letak.pdf"
            with vir.open("wb") as handle:
                writer.write(handle)
            bin_ = root / "bin"
            bin_.mkdir()
            pid_datoteka = root / "pid"
            spanec = root / "spanec.py"
            spanec.write_text(f"import os, time\nopen(r'{pid_datoteka}', 'w').write(str(os.getpid()))\n"
                              "time.sleep(300)\n")
            (bin_ / "pdftoppm.cmd").write_text(f'@"{sys.executable}" "{spanec}"\r\n')
            (bin_ / "tesseract.cmd").write_text("@exit /b 0\r\n")
            with unittest.mock.patch.dict(os.environ, {"PATH": f"{bin_};{os.environ['PATH']}"}):
                with self.assertRaises(strani.CasPotekel):
                    strani.filter_pdf_izolirano(vir, root / "m.pdf", use_ocr=True,
                                                trdi_rok_s=15, page_timeout_s=300)
            pid = int(pid_datoteka.read_text())
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.OpenProcess.restype = wintypes.HANDLE
            k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            ziv = True
            for _ in range(50):
                h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if not h:
                    ziv = False
                    break
                koda = wintypes.DWORD()
                k.GetExitCodeProcess(h, ctypes.byref(koda))
                k.CloseHandle(h)
                if koda.value != 259:  # STILL_ACTIVE
                    ziv = False
                    break
                time.sleep(0.2)
            if ziv:
                h = k.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
                k.TerminateProcess(h, 1)
                k.CloseHandle(h)
                self.fail("zataknjen pdftoppm je preživel uboj otroka")
