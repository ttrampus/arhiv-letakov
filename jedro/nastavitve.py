from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import izbor
from .naslovi import mask

CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

PRIVZETI_URNIK = "dnevno 06:00"

IME = "arhiv-letakov"


def je_zapakiran() -> bool:
    """Teče iz enodatotečnega .exe, ki ga naredi PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def domaca_mapa() -> Path:
    """Kje iskati nastavitve.yaml: %PROGRAMDATA%, mapa ob .exe ali koren projekta."""
    if je_zapakiran():
        ob_programu = Path(sys.executable).resolve().parent
        programdata = os.environ.get("PROGRAMDATA")
        if programdata:
            skupna = Path(programdata) / IME
            if (skupna / "nastavitve.yaml").exists():
                return skupna
        return ob_programu
    return Path(__file__).resolve().parent.parent


def je_omrezna_pot(path: Path) -> bool:
    """Pot na SMB delnici (\\\\streznik\\delnica\\... ali zamenjani pogon ni zajet)."""
    return str(path).startswith("\\\\") or str(path).startswith("//")


def je_zamenjan_pogon(path: Path) -> bool:
    """Zamenjan omrežni pogon (Z:), ki ga opravilo pod servisnim računom ne vidi."""
    if os.name != "nt":
        return False
    pogon = os.path.splitdrive(str(path))[0]
    if len(pogon) != 2 or pogon[1] != ":":
        return False
    try:
        import ctypes
        return ctypes.windll.kernel32.GetDriveTypeW(pogon + "\\") == 4  # DRIVE_REMOTE
    except (AttributeError, OSError):
        return False


class NapacneNastavitve(ValueError):
    """Vrednost v nastavitve.yaml je neuporabna; sporočilo pove katera."""


@dataclass
class Config:
    root: Path
    config_path: Path
    archive_dir: Path
    meat_dir: Path
    db_path: Path
    log_dir: Path
    schedule: str = PRIVZETI_URNIK
    request_timeout: int = 60
    download_timeout: int = 900
    delay_between_requests: float = 2.0
    max_retries: int = 3
    user_agent: str = CHROME_UA
    proxy: str = ""
    max_pdf_mb: int = 150
    max_image_mb: int = 25
    max_flyer_mb: int = 400
    max_images: int = 200
    max_redirects: int = 5
    max_page_mb: int = 20
    max_pages: int = 300
    pdf_budget_s: int = 900
    max_memory_mb: int = 2048
    ocr_page_timeout_s: int = 60
    extra_hosts: dict[str, list[str]] = field(default_factory=dict)
    allow_http: bool = False
    stores: dict[str, bool] = field(default_factory=dict)
    only_food: bool = True
    max_validity_days: int = 21
    deny_keywords: list[str] = field(default_factory=list)
    allow_keywords: list[str] = field(default_factory=list)
    meat_enabled: bool = True
    meat_ocr: bool = True
    notify_after: int = 3
    notify_webhook: str = ""
    notify_command: str = ""

    def store_enabled(self, name: str) -> bool:
        return self.stores.get(name, True)

    @property
    def lock_path(self) -> Path:
        return self.db_path.with_name(self.db_path.name + ".lock")

    @property
    def proxy_za_izpis(self) -> str:
        """Posrednik brez poverilnic, za dnevnik."""
        return mask(self.proxy)

    def opozorila(self) -> list[str]:
        """Nastavitve, ki bodo delale težave."""
        tezave = []
        for ime, pot in (("arhiv", self.archive_dir), ("mesne kopije", self.meat_dir)):
            if je_zamenjan_pogon(pot):
                tezave.append(f"{ime} je na zamenjanem omrežnem pogonu ({pot}); servisni "
                              "račun te črke ne vidi, uporabi pot UNC (\\\\streznik\\delnica)")
            # Ime letaka doda do ~110 znakov; Windows brez LongPathsEnabled
            # ne prenese poti, daljših od 260.
            if os.name == "nt" and len(str(pot)) > 140:
                tezave.append(f"pot za {ime} je dolga {len(str(pot))} znakov; skupaj z imeni "
                              "letakov lahko preseže mejo Windows (260)")
        if je_omrezna_pot(self.db_path):
            tezave.append(
                f"baza je na omrežni poti ({self.db_path}); SQLite se čez SMB ne "
                "zaklepa zanesljivo, zato jo prestavi na lokalni disk")
        if je_omrezna_pot(self.log_dir):
            tezave.append(f"mapa dnevnikov je na omrežni poti ({self.log_dir}); "
                          "dnevnik naj ostane lokalen")
        return tezave


def _mape(raw: dict, key: str) -> dict[str, list[str]]:
    """Dodatni gostitelji: seznam velja za vse trgovine, slovar po trgovinah."""
    value = raw.get(key)
    if not value:
        return {}
    if isinstance(value, list):
        return {"*": [str(v) for v in value]}
    return {str(k): [str(x) for x in (v or [])] for k, v in value.items()}


def load(path: Path | str | None = None) -> Config:
    default = domaca_mapa() / "nastavitve.yaml"
    path = path or os.environ.get("ARHIV_NASTAVITVE")
    config_path = (Path(path) if path else default).expanduser()
    # UNC poti resolve() na ne-Windows pokvari, absolutne poti pa ne rabijo tega.
    config_path = config_path if je_omrezna_pot(config_path) else config_path.resolve()
    root = config_path.parent
    raw = {}
    if config_path.exists():
        # utf-8-sig: Windows PowerShell 5.1 datoteko zapiše z BOM.
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(raw, dict):
        raise NapacneNastavitve(f"{config_path} ni slovar nastavitev")

    def resolve(value: str) -> Path:
        p = Path(str(value)).expanduser()
        if je_omrezna_pot(p) or p.is_absolute():
            return p
        return root / p

    omrezje = raw.get("omrezje") or {}
    hrana = raw.get("izbor") or {}
    meso = raw.get("mesne_strani") or {}
    obvestila = raw.get("obvescanje") or {}
    meje = raw.get("meje") or {}

    cfg = Config(
        root=root,
        config_path=config_path,
        archive_dir=resolve(raw.get("mapa_arhiva", "arhiv")),
        meat_dir=resolve(meso.get("mapa", "arhiv-meso")),
        db_path=resolve(raw.get("baza", "arhiv.db")),
        log_dir=resolve(raw.get("mapa_dnevnikov", "dnevniki")),
        schedule=str(raw.get("urnik", PRIVZETI_URNIK)),
        request_timeout=int(omrezje.get("cas_zahteve", 60)),
        download_timeout=int(omrezje.get("cas_prenosa", 900)),
        delay_between_requests=float(omrezje.get("premor_med_zahtevami", 2.0)),
        max_retries=int(omrezje.get("poskusi", 3)),
        user_agent=omrezje.get("user_agent") or CHROME_UA,
        proxy=str(omrezje.get("posrednik") or os.environ.get("HTTPS_PROXY")
                  or os.environ.get("https_proxy") or ""),
        max_pdf_mb=int(meje.get("najvecji_pdf_mb", 150)),
        max_image_mb=int(meje.get("najvecja_slika_mb", 25)),
        max_flyer_mb=int(meje.get("najvecji_letak_skupaj_mb", 400)),
        max_images=int(meje.get("najvec_slik", 200)),
        max_redirects=int(meje.get("najvec_preusmeritev", 5)),
        max_page_mb=int(meje.get("najvecja_stran_mb", 20)),
        max_pages=int(meje.get("najvec_strani", 300)),
        pdf_budget_s=int(meje.get("cas_obdelave_pdf_s", 900)),
        max_memory_mb=int(meje.get("najvec_pomnilnika_mb", 2048)),
        ocr_page_timeout_s=int(meje.get("cas_ocr_strani_s", 60)),
        extra_hosts=_mape(omrezje, "dovoljeni_gostitelji"),
        allow_http=bool(omrezje.get("dovoli_http", False)),
        stores={name: bool((s or {}).get("vklopljeno", True))
                for name, s in (raw.get("trgovine") or {}).items()},
        only_food=bool(hrana.get("samo_zivila", True)),
        max_validity_days=int(hrana.get("najvec_dni_veljavnosti", izbor.DEFAULT_MAX_DAYS)),
        deny_keywords=list(hrana.get("zavrni_besede") or izbor.DEFAULT_DENY),
        allow_keywords=list(hrana.get("sprejmi_besede") or izbor.DEFAULT_ALLOW),
        meat_enabled=bool(meso.get("vklopljeno", True)),
        meat_ocr=bool(meso.get("ocr", True)),
        notify_after=int(obvestila.get("po_neuspehih", 3)),
        notify_webhook=str(obvestila.get("webhook") or ""),
        notify_command=str(obvestila.get("ukaz") or ""),
    )
    _preveri(cfg)
    return cfg


def _preveri(cfg: Config) -> None:
    """Meje morajo biti pozitivne, sicer program tiho ne dela ničesar."""
    pozitivne = {
        "omrezje.cas_zahteve": cfg.request_timeout,
        "omrezje.cas_prenosa": cfg.download_timeout,
        "meje.najvecji_pdf_mb": cfg.max_pdf_mb,
        "meje.najvecja_slika_mb": cfg.max_image_mb,
        "meje.najvecji_letak_skupaj_mb": cfg.max_flyer_mb,
        "meje.najvec_slik": cfg.max_images,
        "meje.najvecja_stran_mb": cfg.max_page_mb,
        "meje.najvec_strani": cfg.max_pages,
        "meje.cas_obdelave_pdf_s": cfg.pdf_budget_s,
        "meje.najvec_pomnilnika_mb": cfg.max_memory_mb,
        "meje.cas_ocr_strani_s": cfg.ocr_page_timeout_s,
    }
    for ime, vrednost in pozitivne.items():
        if vrednost <= 0:
            raise NapacneNastavitve(f"{ime} mora biti večje od 0, je {vrednost}")
    if cfg.max_retries < 0 or cfg.max_redirects < 0 or cfg.delay_between_requests < 0:
        raise NapacneNastavitve("omrezje.poskusi, meje.najvec_preusmeritev in "
                                "omrezje.premor_med_zahtevami ne smejo biti negativni")
