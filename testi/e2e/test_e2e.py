"""E2E: celoten program proti pravim trgovinam, kot bo tekel pri naročniku.

Program se kliče kot zunanji proces, tako kot ga kliče Task Scheduler: izvorna
koda ali zgrajeni arhiv-letakov.exe. Rezultat preverimo na disku in v bazi, ne
v izpisu. V testu tečeta pravi posrednik HTTP (CONNECT) in prejemnik webhookov.

Teče samo na izrecno zahtevo, ker gre na splet in traja 10-20 minut:

    ARHIV_E2E=1 python -m pytest testi/e2e -v

Drug program (npr. zgrajeni .exe pod Wine):

    ARHIV_E2E=1 ARHIV_PROGRAM="wine dist/arhiv-letakov/arhiv-letakov.exe" \\
        ARHIV_PREDPONA="Z:" python -m pytest testi/e2e -v
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import select
import shlex
import socket
import socketserver
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

pytestmark = pytest.mark.skipif(os.environ.get("ARHIV_E2E") != "1",
                                reason="E2E gre na splet; vklopi z ARHIV_E2E=1")

KOREN = Path(__file__).resolve().parents[2]

def _program() -> list[str]:
    vrednost = os.environ.get("ARHIV_PROGRAM", "")
    if not vrednost:
        return [sys.executable, str(KOREN / "letaki.py")]
    # Pot do .exe na Windows vsebuje poševnice, ki bi jih shlex v načinu POSIX pobral.
    if Path(vrednost).exists():
        return [vrednost]
    return shlex.split(vrednost, posix=(os.name != "nt"))


PROGRAM = _program()
# Začasna mapa programa, kot jo vidi ta proces (pod Wine je drugje kot naša).
ZACASNA = Path(os.environ.get("ARHIV_ZACASNA") or tempfile.gettempdir())
PREDPONA = os.environ.get("ARHIV_PREDPONA", "")
TRGOVINE = ["mercator", "tus", "spar", "leclerc", "lidl", "hofer", "eurospin"]


# --- pripomočki ---------------------------------------------------------------

def pot(p: Path) -> str:
    """Pot, kot jo razume program (pod Wine z Z: spredaj)."""
    return PREDPONA + str(p)


def nastavitve(mapa: Path, **spremembe) -> Path:
    """Zapiše nastavitve.yaml v mapo; spremembe so gnezdeni ključi (omrezje={...})."""
    mapa.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load((KOREN / "nastavitve.primer.yaml").read_text(encoding="utf-8"))
    cfg["urnik"] = "ročno"
    cfg["omrezje"]["premor_med_zahtevami"] = 1.0
    for kljuc, vrednost in spremembe.items():
        if isinstance(vrednost, dict):
            cfg.setdefault(kljuc, {}).update(vrednost)
        else:
            cfg[kljuc] = vrednost
    datoteka = mapa / "nastavitve.yaml"
    datoteka.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return datoteka


def zazeni(cfg: Path, *argumenti: str, cas: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run([*PROGRAM, "--nastavitve", pot(cfg), *argumenti],
                          cwd=cfg.parent, capture_output=True, timeout=cas)


def dnevnik(cfg: Path) -> str:
    datoteka = cfg.parent / "dnevniki" / "arhiv-letakov.log"
    return datoteka.read_text(encoding="utf-8", errors="replace") if datoteka.exists() else ""


def tezave(cfg: Path) -> str:
    """Vse napake in opozorila iz dnevnika, za sporočilo ob neuspehu."""
    return "\n".join(v for v in dnevnik(cfg).splitlines()
                     if " ERROR " in v or " WARNING " in v or "ni uspelo" in v)


def vrstice_baze(cfg: Path, poizvedba: str) -> list[sqlite3.Row]:
    povezava = sqlite3.connect(cfg.parent / "arhiv.db")
    povezava.row_factory = sqlite3.Row
    try:
        return povezava.execute(poizvedba).fetchall()
    finally:
        povezava.close()


def lokalna(pot_v_bazi: str, cfg: Path) -> Path:
    """Pot iz baze (pod Windows Z:\\...) nazaj v pot na tem sistemu."""
    if PREDPONA and pot_v_bazi.startswith(PREDPONA):
        return Path(pot_v_bazi[len(PREDPONA):].replace("\\", "/"))
    return Path(pot_v_bazi)


class _Streznik(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class Posrednik:
    """Pravi posrednik HTTP CONNECT za teste.

    Beleži, kam se je program povezal; zna zahtevati prijavo Basic, vedno
    vrniti 407 (kot posrednik s prijavo Windows) ali zavrniti gostitelje, ki
    jih "požarni zid" ne pozna.
    """

    def __init__(self, prijava: tuple[str, str] | None = None, vedno_407: bool = False,
                 blokirani: tuple[str, ...] = ()):
        self.povezave: list[str] = []
        self.prijava = prijava
        zunanji = self

        class Obdelava(socketserver.StreamRequestHandler):
            def handle(self):
                glava = b""
                while b"\r\n\r\n" not in glava:
                    kos = self.connection.recv(4096)
                    if not kos:
                        return
                    glava += kos
                vrstice = glava.decode("latin-1").split("\r\n")
                metoda, cilj, _ = vrstice[0].split(" ", 2)
                glave = {v.split(":", 1)[0].lower(): v.split(":", 1)[1].strip()
                         for v in vrstice[1:] if ":" in v}
                zunanji.povezave.append(f"{metoda} {cilj}")
                if vedno_407 or (zunanji.prijava and glave.get("proxy-authorization") !=
                                 "Basic " + base64.b64encode(
                                     ":".join(zunanji.prijava).encode()).decode()):
                    self.connection.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                                            b"Proxy-Authenticate: Negotiate\r\n"
                                            b"Content-Length: 0\r\n\r\n")
                    return
                host, _, vrata = cilj.rpartition(":")
                if metoda != "CONNECT" or host in blokirani:
                    self.connection.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                    return
                try:
                    naprej = socket.create_connection((host, int(vrata)), timeout=30)
                except OSError:
                    self.connection.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                    return
                self.connection.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                vticnici = [self.connection, naprej]
                try:
                    while True:
                        pripravljene, _, _ = select.select(vticnici, [], [], 60)
                        if not pripravljene:
                            break
                        for v in pripravljene:
                            podatki = v.recv(65536)
                            if not podatki:
                                return
                            (naprej if v is self.connection else self.connection).sendall(podatki)
                except OSError:
                    pass
                finally:
                    naprej.close()

        self.streznik = _Streznik(("127.0.0.1", 0), Obdelava)
        threading.Thread(target=self.streznik.serve_forever, daemon=True).start()
        self.vrata = self.streznik.server_address[1]

    def naslov(self) -> str:
        if self.prijava:
            return f"http://{self.prijava[0]}:{self.prijava[1]}@127.0.0.1:{self.vrata}"
        return f"http://127.0.0.1:{self.vrata}"

    def ustavi(self):
        self.streznik.shutdown()
        self.streznik.server_close()


class Webhook:
    """Prejemnik obvestil: zapomni si vsak POST."""

    def __init__(self):
        self.sporocila: list[str] = []
        zunanji = self

        class Obdelava(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                dolzina = int(self.headers.get("Content-Length", 0))
                zunanji.sporocila.append(json.loads(self.rfile.read(dolzina))["text"])
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.streznik = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Obdelava)
        threading.Thread(target=self.streznik.serve_forever, daemon=True).start()

    def naslov(self) -> str:
        return f"http://127.0.0.1:{self.streznik.server_address[1]}/"

    def ustavi(self):
        self.streznik.shutdown()
        self.streznik.server_close()


# --- glavni zajem: vseh sedem trgovin -------------------------------------------

@pytest.fixture(scope="module")
def glavni(tmp_path_factory):
    """En pravi zajem vseh trgovin z mesnimi kopijami; ostali testi ga pregledajo."""
    cfg = nastavitve(tmp_path_factory.mktemp("glavni"))
    zacasne_pred = set(ZACASNA.glob("arhiv-letakov-pdf-*"))
    zacetek = time.monotonic()
    izid = zazeni(cfg, "prenesi")
    return {"cfg": cfg, "izid": izid, "trajanje": time.monotonic() - zacetek,
            "zacasne_pred": zacasne_pred}


def test_zajem_uspe(glavni):
    izid = glavni["izid"]
    assert izid.returncode == 0, tezave(glavni["cfg"])
    besedilo = dnevnik(glavni["cfg"])
    assert "Konec: preneseno" in besedilo
    assert " ERROR " not in besedilo, [v for v in besedilo.splitlines() if " ERROR " in v]


def test_vseh_sedem_trgovin_ima_letake(glavni):
    trgovine = {r["store"] for r in vrstice_baze(glavni["cfg"], "SELECT store FROM magazines")}
    assert trgovine == set(TRGOVINE), f"manjkajo: {set(TRGOVINE) - trgovine}"


def test_vsak_letak_je_cel_in_veljaven_pdf(glavni):
    vrstice = vrstice_baze(glavni["cfg"], "SELECT * FROM magazines")
    assert len(vrstice) >= len(TRGOVINE)
    for vrstica in vrstice:
        datoteka = lokalna(vrstica["local_path"], glavni["cfg"])
        podatki = datoteka.read_bytes()
        assert podatki.startswith(b"%PDF"), datoteka
        assert len(podatki) == vrstica["bytes"], datoteka
        assert hashlib.sha256(podatki).hexdigest() == vrstica["sha256"], datoteka
        assert len(PdfReader(str(datoteka)).pages) >= 1, datoteka
        # Arhiv je urejen po trgovini in letu.
        assert datoteka.parent.parent.name == vrstica["store"]


def test_mesne_kopije_ustrezajo(glavni):
    vrstice = vrstice_baze(glavni["cfg"], """
        SELECT m.local_path AS izvirnik, v.local_path AS meso, v.source_pages, v.kept_pages
        FROM meat_versions v JOIN magazines m ON m.id = v.magazine_id""")
    letakov = vrstice_baze(glavni["cfg"], "SELECT COUNT(*) AS n FROM magazines")[0]["n"]
    assert len(vrstice) == letakov, "vsak letak mora imeti zapis o mesni kopiji"
    for vrstica in vrstice:
        izvirnik = lokalna(vrstica["izvirnik"], glavni["cfg"])
        assert len(PdfReader(str(izvirnik)).pages) == vrstica["source_pages"]
        assert 0 <= vrstica["kept_pages"] <= vrstica["source_pages"]
        meso = lokalna(vrstica["meso"], glavni["cfg"])
        if vrstica["kept_pages"]:
            assert len(PdfReader(str(meso)).pages) == vrstica["kept_pages"], meso
        else:
            assert not meso.exists(), meso
    # Mesnih strani ni povsod, vsaj nekje pa so.
    assert any(v["kept_pages"] for v in vrstice)


def test_ni_ostankov(glavni):
    mapa = glavni["cfg"].parent
    ostanki = [p for p in mapa.rglob("*") if p.name.endswith(".part")
               or p.name.startswith(".arhiv-letakov-poskus")]
    assert not ostanki, ostanki
    # Mapa letaka iz slik po sestavljanju ne sme ostati.
    assert not [p for p in (mapa / "arhiv").rglob("*") if p.is_dir() and p.parent.name.isdigit()]
    zacasne = set(ZACASNA.glob("arhiv-letakov-pdf-*"))
    assert zacasne <= glavni["zacasne_pred"], zacasne - glavni["zacasne_pred"]


def test_stanje_za_nadzor(glavni):
    izid = zazeni(glavni["cfg"], "stanje", "--json", cas=120)
    assert izid.returncode == 0, izid.stdout
    porocilo = json.loads(izid.stdout)
    assert porocilo["v_redu"] is True
    assert porocilo["pokvarjene"] == {}
    stevilo = vrstice_baze(glavni["cfg"], "SELECT COUNT(*) AS n FROM magazines")[0]["n"]
    assert porocilo["katalogov"] == stevilo
    assert set(porocilo["trgovine"]) == set(TRGOVINE)


def test_drugi_zagon_ne_prenese_nicesar(glavni):
    cfg = glavni["cfg"]
    pred = {p: p.stat().st_mtime_ns for p in (cfg.parent / "arhiv").rglob("*.pdf")}
    izid = zazeni(cfg, "prenesi")
    assert izid.returncode == 0, tezave(cfg)
    zadnji = [v for v in dnevnik(cfg).splitlines() if "Konec:" in v][-1]
    assert "preneseno 0," in zadnji, zadnji
    po = {p: p.stat().st_mtime_ns for p in (cfg.parent / "arhiv").rglob("*.pdf")}
    assert po == pred, "drugi zagon je spremenil ali dodal datoteke"


def test_seznam_pregled_gostitelji(glavni):
    for ukaz in (["seznam"], ["pregled"], ["gostitelji"], ["gostitelji", "--json"]):
        izid = zazeni(glavni["cfg"], *ukaz, cas=120)
        assert izid.returncode == 0, (ukaz, izid.stdout, izid.stderr)
    gostitelji = json.loads(zazeni(glavni["cfg"], "gostitelji", "--json", cas=120).stdout)
    assert "www.hofer.si" in gostitelji and "cdn.ipaper.io" in gostitelji


def test_mesne_kopije_znova(glavni):
    cfg = glavni["cfg"]
    pred = {r["meso"]: r["kept_pages"] for r in vrstice_baze(
        cfg, "SELECT local_path AS meso, kept_pages FROM meat_versions")}
    izid = zazeni(cfg, "meso", "--znova")
    assert izid.returncode == 0, tezave(cfg)
    po = {r["meso"]: r["kept_pages"] for r in vrstice_baze(
        cfg, "SELECT local_path AS meso, kept_pages FROM meat_versions")}
    assert po == pred


# --- hkratna zagona ---------------------------------------------------------------

def test_drugi_hkratni_zagon_odstopi(tmp_path):
    cfg = nastavitve(tmp_path / "hkrati", mesne_strani={"vklopljeno": False})
    prvi = subprocess.Popen([*PROGRAM, "--nastavitve", pot(cfg), "prenesi",
                             "--trgovina", "lidl", "--trgovina", "spar"],
                            cwd=cfg.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(300):
            if "prenašam" in dnevnik(cfg) or prvi.poll() is not None:
                break
            time.sleep(0.5)
        assert prvi.poll() is None, "prvi zagon je končal, preden smo preizkusili drugega"
        drugi = zazeni(cfg, "prenesi", "--trgovina", "eurospin", cas=300)
        assert drugi.returncode == 0
        assert "drug zagon že teče" in dnevnik(cfg)
    finally:
        prvi.wait(timeout=1800)
    assert prvi.returncode == 0, tezave(cfg)


# --- okvare, ki morajo biti vidne -----------------------------------------------

def test_nedosegljiv_arhiv_konca_z_napako_in_obvestilom(tmp_path):
    webhook = Webhook()
    try:
        (tmp_path / "ovira").write_text("to je datoteka, ne mapa")
        cfg = nastavitve(tmp_path / "zaklenjen", mapa_arhiva=pot(tmp_path / "ovira" / "arhiv"),
                         obvescanje={"webhook": webhook.naslov()})
        izid = zazeni(cfg, "prenesi", "--trgovina", "eurospin", cas=300)
        assert izid.returncode == 1
        assert "ni mogoče pisati" in dnevnik(cfg)
        assert webhook.sporocila and "ni mogoče pisati" in webhook.sporocila[0]
    finally:
        webhook.ustavi()


def test_meja_velikosti_ustavi_prevelik_letak(tmp_path):
    cfg = nastavitve(tmp_path / "meja", meje={"najvecji_pdf_mb": 1},
                     mesne_strani={"vklopljeno": False})
    izid = zazeni(cfg, "prenesi", "--trgovina", "eurospin", cas=600)
    assert izid.returncode == 1
    besedilo = dnevnik(cfg)
    assert "MB, meja je 1 MB" in besedilo or "presegel 1 MB" in besedilo
    assert not list((cfg.parent / "arhiv").rglob("*.pdf"))
    assert not list((cfg.parent / "arhiv").rglob("*.part"))


# --- posrednik ---------------------------------------------------------------------

def test_zajem_skozi_posrednika(tmp_path):
    posrednik = Posrednik()
    try:
        cfg = nastavitve(tmp_path / "posrednik", omrezje={"posrednik": posrednik.naslov()},
                         mesne_strani={"vklopljeno": False})
        izid = zazeni(cfg, "prenesi", "--trgovina", "eurospin", "--trgovina", "spar", cas=900)
        assert izid.returncode == 0, tezave(cfg)
        assert list((cfg.parent / "arhiv" / "eurospin").rglob("*.pdf"))
        assert list((cfg.parent / "arhiv" / "spar").rglob("*.pdf"))
        # Vse je šlo skozi posrednika, samo na dovoljene gostitelje in vrata 443.
        assert posrednik.povezave
        dovoljeni = set(json.loads(zazeni(cfg, "gostitelji", "--json", cas=120).stdout))
        for povezava in posrednik.povezave:
            metoda, cilj = povezava.split(" ")
            host, _, vrata = cilj.rpartition(":")
            assert metoda == "CONNECT" and vrata == "443", povezava
            assert host in dovoljeni, povezava
    finally:
        posrednik.ustavi()


def test_posrednik_s_prijavo_in_geslo_ni_v_dnevniku(tmp_path):
    geslo = "Skr1vn0-Geslo-e2e"
    posrednik = Posrednik(prijava=("svc-letaki", geslo))
    try:
        cfg = nastavitve(tmp_path / "prijava", omrezje={"posrednik": posrednik.naslov()},
                         mesne_strani={"vklopljeno": False})
        izid = zazeni(cfg, "prenesi", "--trgovina", "eurospin", cas=600)
        assert izid.returncode == 0, tezave(cfg)
        assert list((cfg.parent / "arhiv").rglob("*.pdf"))
        vse = dnevnik(cfg) + izid.stdout.decode(errors="replace") + izid.stderr.decode(errors="replace")
        assert geslo not in vse
        assert "svc-letaki" not in vse
        assert f"***:***@127.0.0.1:{posrednik.vrata}" in dnevnik(cfg)
    finally:
        posrednik.ustavi()


def test_posrednik_s_prijavo_windows_da_jasno_napako(tmp_path):
    posrednik = Posrednik(vedno_407=True)
    try:
        cfg = nastavitve(tmp_path / "p407", omrezje={"posrednik": posrednik.naslov()})
        izid = zazeni(cfg, "prenesi", "--trgovina", "eurospin", "--trgovina", "mercator", cas=600)
        assert izid.returncode == 1
        besedilo = dnevnik(cfg)
        assert "posrednik zahteva prijavo (407)" in besedilo
        assert "Nobena trgovina ni dosegljiva" in besedilo
    finally:
        posrednik.ustavi()


def test_pozarni_zid_brez_enega_gostitelja(tmp_path):
    # Skrbnik je pozabil cdn.ipaper.io: Sparova stran gre, datoteke pa ne.
    posrednik = Posrednik(blokirani=("cdn.ipaper.io",))
    try:
        cfg = nastavitve(tmp_path / "zid", omrezje={"posrednik": posrednik.naslov()},
                         mesne_strani={"vklopljeno": False},
                         obvescanje={"po_neuspehih": 1})
        izid = zazeni(cfg, "prenesi", "--trgovina", "spar", "--trgovina", "eurospin", cas=900)
        assert izid.returncode == 1
        assert not list((cfg.parent / "arhiv").rglob("spar/**/*.pdf"))
        assert list((cfg.parent / "arhiv").rglob("eurospin/**/*.pdf"))
        stanje = json.loads(zazeni(cfg, "stanje", "--json", cas=120).stdout)
        assert "spar" in stanje["pokvarjene"] and "eurospin" not in stanje["pokvarjene"]
    finally:
        posrednik.ustavi()
