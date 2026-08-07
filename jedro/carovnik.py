from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from . import urnik as urnik_modul
from .nastavitve import CHROME_UA

IZBIRE_URNIKA = [
    ("dnevno 06:00", "vsako jutro ob 06:00 (priporočeno)"),
    ("dnevno 06:00,18:00", "dvakrat na dan, zjutraj in zvečer"),
    ("cet 06:00", "enkrat na teden v četrtek, ko izide največ letakov"),
    ("pon,cet 06:00", "dvakrat na teden, v ponedeljek in četrtek"),
]


def run(config_path: Path, stores: list, *, reconfigure: bool = False) -> Path:
    _headline(config_path, reconfigure)

    root = config_path.resolve().parent
    answers = {
        "archive_dir": _ask_archive_dir(root),
        "stores": _ask_stores(stores),
        "only_food": _ask_yes_no(
            "Naj zbira samo tedenske živilske letake?\n"
            "  Če odgovoriš ne, arhivira tudi tematske brošure (šolske potrebščine, nakit ...)",
            default=True),
    }
    answers["meat"] = _ask_yes_no(
        "Naj ob vsakem letaku shrani še kopijo samo s stranmi, na katerih je meso?",
        default=True)
    answers["schedule"] = _ask_schedule()

    _write_config(config_path, answers, stores)
    print(f"\nZapisano v {config_path}")

    _offer_timer(root, config_path, answers["schedule"])
    _closing(answers)
    return config_path


def _ask_archive_dir(root: Path) -> str:
    answer = _ask("Kam naj shranjuje kataloge?", default="arhiv")
    path = Path(answer).expanduser()
    shown = path if path.is_absolute() else root / path
    print(f"  -> {shown}")
    return answer


def _ask_stores(stores: list) -> dict[str, bool]:
    print("\nTrgovine:")
    for index, store in enumerate(stores, 1):
        note = "  (potrebuje Chromium brez okna)" if store.requires_browser else ""
        print(f"  {index}. {store.label}{note}")

    answer = _ask("Katere? 'vse' ali številke, npr. 1,3,5",
                  default="vse").strip().lower()
    if answer in ("", "vse", "v"):
        return {store.name: True for store in stores}

    picked = set()
    for part in answer.replace(" ", ",").split(","):
        if part.isdigit() and 1 <= int(part) <= len(stores):
            picked.add(stores[int(part) - 1].name)
        else:
            for store in stores:
                if part and store.name.startswith(part):
                    picked.add(store.name)

    if not picked:
        print("  Nič prepoznanega, zato vklapljam vse.")
        return {store.name: True for store in stores}

    chosen = [s.label for s in stores if s.name in picked]
    print(f"  -> {', '.join(chosen)}")
    return {store.name: store.name in picked for store in stores}


def _ask_schedule() -> str:
    print("\nKako pogosto naj preverja, ali so izšli novi katalogi?")
    print("  Trgovine izdajajo tedensko, a ne vse isti dan, preverjanje brez")
    print("  najdb pa traja nekaj sekund. Dnevno je varna izbira.")
    for index, (value, description) in enumerate(IZBIRE_URNIKA, 1):
        print(f"  {index}. {description}")
    print(f"  {len(IZBIRE_URNIKA) + 1}. nikoli, poganjal bom sam")

    answer = _ask("Izberi eno ali napiši svojo, npr. 'tor,pet 07:30'", default="1").strip()

    if answer.isdigit():
        number = int(answer)
        if number == len(IZBIRE_URNIKA) + 1:
            return "ročno"
        if 1 <= number <= len(IZBIRE_URNIKA):
            answer = IZBIRE_URNIKA[number - 1][0]
        else:
            answer = IZBIRE_URNIKA[0][0]
    if urnik_modul.is_manual(answer):
        return "ročno"

    print(f"  -> {answer}  (systemd OnCalendar={urnik_modul.describe(answer)})")
    return answer


def _offer_timer(root: Path, config_path: Path, schedule: str) -> None:
    if urnik_modul.is_manual(schedule):
        print("\nBrez časovnika. Poženi ./letaki prenesi, kadar hočeš.")
        return
    if not shutil.which("systemctl"):
        print("\nTu ni systemd, zato časovnika ni mogoče namestiti samodejno.")
        print(f"Namesto tega dodaj v cron:  {root}/letaki prenesi")
        return
    if not _ask_yes_no(f"Naj časovnik namestim zdaj, da teče {schedule}?", default=True):
        print("Pozneje z: ./letaki urnik namesti")
        return

    oncalendars = urnik_modul.install(root, schedule, config_path)
    print(f"  Nameščeno, zagon {schedule} (OnCalendar={', '.join(oncalendars)})")
    print("  Stanje kadar koli preveriš z: ./letaki urnik")


def _closing(answers: dict) -> None:
    print("\nNastavitev končana.\n")
    print("  ./letaki prenesi --poskusno   poglej, kaj je zunaj, ne prenašaj")
    print("  ./letaki prenesi              prenesi")
    print("  ./letaki                      stanje in vsi ukazi")
    if answers["meat"]:
        from . import strani
        if not strani.ocr_available():
            print("\nOpomba: tesseract ni nameščen, zato letaki brez besedila (Lidl)")
            print("obdržijo vse strani namesto samo mesnih. Popraviš takole:")
            print("  Arch:   sudo pacman -S tesseract tesseract-data-slv poppler")
            print("  Debian: sudo apt install tesseract-ocr tesseract-ocr-slv poppler-utils")


def _write_config(config_path: Path, answers: dict, stores: list) -> None:
    if config_path.exists():
        backup = config_path.with_suffix(".yaml.bak")
        shutil.copy2(config_path, backup)
        print(f"\nPrejšnje nastavitve sem ohranil kot {backup.name}")

    config_path.write_text(_render(answers, stores), encoding="utf-8")


def _render(answers: dict, stores: list) -> str:
    store_lines = "\n".join(
        f"  {store.name}:\n    vklopljeno: {str(answers['stores'][store.name]).lower()}"
        for store in stores
    )
    return f"""\
mapa_arhiva: {answers["archive_dir"]}
baza: arhiv.db
mapa_dnevnikov: dnevniki

# dnevno HH:MM | tedensko HH:MM | pon,cet 06:15 | ročno
urnik: {answers["schedule"]}

omrezje:
  cas_zahteve: 60
  cas_prenosa: 300
  premor_med_zahtevami: 2.0
  poskusi: 3
  user_agent: >-
    {CHROME_UA}

brskalnik:
  brez_okna: true
  cas_ms: 60000

izbor:
  samo_zivila: {str(answers["only_food"]).lower()}
  najvec_dni_veljavnosti: 21
  # zavrni_besede: [šola, zlatarna, ferdo, vinski]
  # sprejmi_besede: [redni katalog, akcijski katalog, letak]

mesne_strani:
  vklopljeno: {str(answers["meat"]).lower()}
  mapa: arhiv-meso
  ocr: true

trgovine:
{store_lines}
"""


def _headline(config_path: Path, reconfigure: bool) -> None:
    print()
    print("=" * 62)
    print("  Arhiv slovenskih trgovinskih letakov: nastavitev")
    print("=" * 62)
    if reconfigure and config_path.exists():
        print("\nNastavljamo znova. Pritisni Enter za predlagani odgovor.")
    else:
        print("\nNekaj vprašanj. Pritisni Enter za predlagani odgovor.")


def _ask(question: str, default: str) -> str:
    print(f"\n{question}")
    try:
        answer = input(f"  [{default}] ").strip()
    except EOFError:
        print()
        return default
    return answer or default


def _ask_yes_no(question: str, default: bool) -> bool:
    hint = "D/n" if default else "d/N"
    print(f"\n{question}")
    while True:
        try:
            answer = input(f"  [{hint}] ").strip().lower()
        except EOFError:
            print()
            return default
        if not answer:
            return default
        if answer in ("d", "da", "y", "yes"):
            return True
        if answer in ("n", "ne", "no"):
            return False
        print("  Odgovori z d ali n.")


def offer_first_run(root: Path) -> None:
    if not _ask_yes_no("Naj prenesem, kar je na voljo zdaj?", default=True):
        return
    print()
    subprocess.run([sys.executable, str(root / "letaki.py"), "prenesi"], cwd=root)
