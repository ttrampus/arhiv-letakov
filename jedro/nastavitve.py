from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import izbor

CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

PRIVZETI_URNIK = "dnevno 06:00"


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
    download_timeout: int = 300
    delay_between_requests: float = 2.0
    max_retries: int = 3
    user_agent: str = CHROME_UA
    browser_headless: bool = True
    browser_timeout: int = 60_000
    stores: dict[str, bool] = field(default_factory=dict)
    only_food: bool = True
    max_validity_days: int = 21
    deny_keywords: list[str] = field(default_factory=list)
    allow_keywords: list[str] = field(default_factory=list)
    meat_enabled: bool = True
    meat_ocr: bool = True

    def store_enabled(self, name: str) -> bool:
        return self.stores.get(name, True)


def load(path: Path | str | None = None) -> Config:
    default = Path(__file__).resolve().parent.parent / "nastavitve.yaml"
    config_path = (Path(path) if path else default).expanduser().resolve()
    root = config_path.parent
    raw = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    def resolve(value: str) -> Path:
        p = Path(value).expanduser()
        return p if p.is_absolute() else root / p

    omrezje = raw.get("omrezje") or {}
    brskalnik = raw.get("brskalnik") or {}
    hrana = raw.get("izbor") or {}
    meso = raw.get("mesne_strani") or {}

    return Config(
        root=root,
        config_path=config_path,
        archive_dir=resolve(raw.get("mapa_arhiva", "arhiv")),
        meat_dir=resolve(meso.get("mapa", "arhiv-meso")),
        db_path=resolve(raw.get("baza", "arhiv.db")),
        log_dir=resolve(raw.get("mapa_dnevnikov", "dnevniki")),
        schedule=str(raw.get("urnik", PRIVZETI_URNIK)),
        request_timeout=int(omrezje.get("cas_zahteve", 60)),
        download_timeout=int(omrezje.get("cas_prenosa", 300)),
        delay_between_requests=float(omrezje.get("premor_med_zahtevami", 2.0)),
        max_retries=int(omrezje.get("poskusi", 3)),
        user_agent=omrezje.get("user_agent") or CHROME_UA,
        browser_headless=bool(brskalnik.get("brez_okna", True)),
        browser_timeout=int(brskalnik.get("cas_ms", 60_000)),
        stores={name: bool((s or {}).get("vklopljeno", True))
                for name, s in (raw.get("trgovine") or {}).items()},
        only_food=bool(hrana.get("samo_zivila", True)),
        max_validity_days=int(hrana.get("najvec_dni_veljavnosti", izbor.DEFAULT_MAX_DAYS)),
        deny_keywords=list(hrana.get("zavrni_besede") or izbor.DEFAULT_DENY),
        allow_keywords=list(hrana.get("sprejmi_besede") or izbor.DEFAULT_ALLOW),
        meat_enabled=bool(meso.get("vklopljeno", True)),
        meat_ocr=bool(meso.get("ocr", True)),
    )
