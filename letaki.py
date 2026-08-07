#!/usr/bin/env python3

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jedro import nastavitve as nastavitve_modul
from jedro import izbor, dnevnik, obvestila, strani, urnik, carovnik
from jedro.baza import Archive
from jedro.prenos import fetch_magazine, target_path
from jedro.povezava import Fetchers
from jedro.modeli import Magazine
from trgovine import get_stores
from trgovine.osnova import BaseStore

log = logging.getLogger("letaki")


def cmd_run(args, cfg) -> int:
    if args.all:
        cfg.only_food = False
    if args.no_meat:
        cfg.meat_enabled = False

    with Archive(cfg.db_path) as archive:
        stores = [s for s in get_stores(args.stores)
                  if args.stores or cfg.store_enabled(s.name)]
        if not stores:
            log.error("Nobena trgovina ni vklopljena.")
            return 1

        fetchers = Fetchers(cfg)
        totals = [0, 0, 0]
        broken = []
        try:
            for store in stores:
                try:
                    found, result = process_store(store, fetchers, archive, cfg, args.dry_run)
                    totals = [a + b for a, b in zip(totals, result)]
                    if found:
                        archive.note_store_result(store.name, True)
                    else:
                        archive.note_store_result(store.name, False, "nič najdenega")
                        broken.append(store.name)
                except Exception as exc:
                    log.error("%s: zajem ni uspel: %s", store.name, exc)
                    log.debug("sled napake", exc_info=True)
                    archive.note_store_result(store.name, False, str(exc)[:200])
                    broken.append(store.name)
        finally:
            fetchers.close()

        verb = "bi preneslo" if args.dry_run else "preneseno"
        log.info("Konec: %s %s, %s preskočenih, %s neuspelih",
                 verb, totals[0], totals[1], totals[2])
        if broken:
            log.warning("Trgovine brez rezultata: %s", ", ".join(broken))
        return _report_failures(archive, cfg)


def _report_failures(archive, cfg) -> int:
    failing = archive.failing_stores(cfg.notify_after)
    if not failing:
        return 0
    text = obvestila.message(failing)
    for line in text.splitlines()[1:]:
        log.error(line)
    obvestila.send(cfg, text)
    return 1


def process_store(store: BaseStore, fetchers, archive, cfg, dry_run: bool):
    log.info("=== %s", store.label)
    magazines = store.find_magazines(fetchers)
    found = len(magazines)

    if not magazines:
        log.warning("%s: nič najdenega (postavitev strani se je morda spremenila)", store.name)
        return 0, (0, 0, 0)

    if cfg.only_food:
        magazines = [m for m in magazines if _is_food(m, cfg)]

    log.info("%s: najdenih katalogov: %s", store.name, len(magazines))
    downloaded = skipped = failed = 0

    for magazine in magazines:
        if archive.has_url(magazine.dedupe_key):
            log.info("  preskok (že v arhivu): %s", magazine.describe())
            skipped += 1
            continue

        if dry_run:
            log.info("  NOVO: %s -> %s", magazine.describe(), magazine.dedupe_key)
            downloaded += 1
            continue

        destination = target_path(cfg.archive_dir, magazine, archive.taken_paths())
        log.info("  prenašam: %s", magazine.describe())
        try:
            path, sha256, size = fetch_magazine(magazine, fetchers, destination,
                                                use_browser=store.requires_browser)
        except Exception as exc:
            log.error("  ni uspelo: %s (%s)", magazine.title, exc)
            log.debug("sled napake", exc_info=True)
            failed += 1
            continue

        if archive.has_hash(sha256):
            log.info("  enaka vsebina je že v arhivu, zavržem: %s", magazine.title)
            path.unlink(missing_ok=True)
            skipped += 1
            continue

        if archive.record(magazine, path, sha256, size):
            log.info("  shranjeno %s (%.1f MB)",
                     path.relative_to(cfg.archive_dir), size / 1e6)
            downloaded += 1
            if cfg.meat_enabled:
                build_meat_version(archive, cfg, path)
        else:
            path.unlink(missing_ok=True)
            skipped += 1

    return found, (downloaded, skipped, failed)


def _is_food(magazine: Magazine, cfg) -> bool:
    keep, reason = izbor.is_weekly_food_flyer(
        magazine, cfg.max_validity_days, cfg.deny_keywords, cfg.allow_keywords)
    if not keep:
        log.info("  preskočim %s: ni živilski letak, %s", magazine.title, reason)
    return keep


def meat_path(cfg, original: Path) -> Path | None:
    try:
        return cfg.meat_dir / original.relative_to(cfg.archive_dir)
    except ValueError:
        return None


def build_meat_version(archive, cfg, original: Path) -> None:
    magazine_id = archive.id_for_path(str(original))
    if magazine_id is None:
        return
    destination = meat_path(cfg, original)
    if destination is None:
        log.warning("  %s je zunaj %s, mesne kopije ne delam",
                    original.name, cfg.archive_dir)
        return
    try:
        result = strani.filter_pdf(original, destination, use_ocr=cfg.meat_ocr)
    except Exception as exc:
        log.error("  izbor mesnih strani ni uspel za %s (%s)", original.name, exc)
        log.debug("sled napake", exc_info=True)
        return
    log.info("  samo meso: %s -> %s", result, destination.name)
    archive.record_meat_version(magazine_id, destination, result.total, len(result.kept))


def cmd_meat(args, cfg) -> int:
    with Archive(cfg.db_path) as archive:
        rows = archive.all_rows() if args.rebuild else archive.magazines_without_meat_version()
        todo = [r for r in rows
                if (not args.stores or r["store"] in args.stores)
                and Path(r["local_path"]).exists()]

        if not todo:
            print("Ni dela: vsak letak že ima kopijo samo z mesnimi stranmi.")
            return 0
        if not strani.ocr_available():
            log.warning("tesseract ni nameščen: letaki brez besedila ohranijo vse strani")

        log.info("Gradim mesne kopije za toliko letakov: %s", len(todo))
        for row in todo:
            log.info("%s: %s", row["store"], Path(row["local_path"]).name)
            build_meat_version(archive, cfg, Path(row["local_path"]))

        print()
        for row in archive.meat_summary():
            share = (f"{100 * row['kept_pages'] / row['source_pages']:.0f}%"
                     if row["source_pages"] else "-")
            print(f"  {row['store']:<9} {row['files']:>2} datotek   "
                  f"{row['source_pages']:>4} -> {row['kept_pages']:>3} strani  ({share})")
    return 0


RUN_FLAGS = ("--trgovina", "--poskusno", "--vse", "--brez-mesa")

HELP = """\
Ukazi
  ./letaki prenesi          prenese vse novo iz vsake vklopljene trgovine
        --poskusno          samo pokaže, kaj je novega, ne prenese ničesar
        --trgovina lidl     samo ta trgovina (lahko večkrat)
        --vse               skupaj s tematskimi brošurami
        --brez-mesa         brez kopij samo z mesnimi stranmi
  ./letaki seznam           kaj je v arhivu, po trgovinah
  ./letaki meso             zgradi kopije samo z mesnimi stranmi
        --znova             naredi jih na novo, npr. po urejanju jedro/meso.py
  ./letaki pregled          datoteke v arhivu, ki jih izbor danes ne bi zbral
        --izbrisi           in jih izbriše
  ./letaki urnik            ali časovnik teče in kdaj je naslednji zagon
        namesti / odstrani  vklopi ali izklopi ga
  ./letaki nastavitev       znova odgovori na vprašanja, prepiše nastavitve.yaml

Dodaj -p kateremu koli ukazu, da vidiš vsako zahtevo in odločitev.
Nastavitve so v {config_path}"""


def cmd_home(cfg) -> int:
    print("Arhiv slovenskih trgovinskih letakov")
    print("Tedenski katalogi sedmih slovenskih trgovin in ob vsakem kopija,")
    print("ki ima samo strani z mesom.\n")

    with Archive(cfg.db_path) as archive:
        rows = archive.summary()
        failing = archive.failing_stores(cfg.notify_after)
    if rows:
        total = sum(row["count"] for row in rows)
        latest = max(row["latest"] for row in rows)[:10]
        print(f"  Arhiv     {total} katalogov iz {len(rows)} trgovin, "
              f"nazadnje preneseno {latest}")
        print(f"            {cfg.archive_dir}")
    else:
        print("  Arhiv     zaenkrat prazen, napolni ga ./letaki prenesi")

    if urnik.installed():
        print(f"  Časovnik  teče, zagon {cfg.schedule}")
    else:
        print("  Časovnik  ni nameščen, poženi ./letaki urnik namesti")

    for row in failing:
        print(f"  Težava    {row['store']}: {row['failures']} zagonov zapored"
              f" brez rezultata ({row['reason'] or 'neznano'})")

    print()
    print(HELP.format(config_path=cfg.config_path))
    return 0


def cmd_list(args, cfg) -> int:
    with Archive(cfg.db_path) as archive:
        rows = archive.summary()
        if not rows:
            print("Arhiv je prazen. Poženi: ./letaki prenesi")
            return 0
        for row in rows:
            print(f"{row['store']:<10} {row['count']:>3} katalogov   "
                  f"nazadnje {row['latest'][:10]}")
        print(f"\nCeli katalogi:   {cfg.archive_dir}")
        print(f"Samo mesne strani: {cfg.meat_dir}")
    return 0


def cmd_audit(args, cfg) -> int:
    with Archive(cfg.db_path) as archive:
        rejected = []
        for row in archive.all_rows():
            magazine = Magazine(store=row["store"], title=row["title"] or "", source_url="",
                                date_from=_date(row["date_from"]), date_to=_date(row["date_to"]))
            keep, reason = izbor.is_weekly_food_flyer(
                magazine, cfg.max_validity_days, cfg.deny_keywords, cfg.allow_keywords)
            if not keep:
                rejected.append((row, reason))

        if not rejected:
            print("Vse v arhivu ustreza izboru živilskih letakov.")
            return 0

        print(f"Toliko katalogov v arhivu danes ne bi bilo zbranih: {len(rejected)}\n")
        for row, reason in rejected:
            print(f"  {row['store']:<9} {row['title'][:52]:<54} {reason}")

        if not args.purge:
            print("\nIzbrišeš jih z: ./letaki pregled --izbrisi")
            return 0

        for row, _ in rejected:
            original = Path(row["local_path"])
            original.unlink(missing_ok=True)
            meat = meat_path(cfg, original)
            if meat:
                meat.unlink(missing_ok=True)
            archive.delete(row["id"])
        print(f"\nIzbrisanih katalogov: {len(rejected)}")
    return 0


def cmd_setup(args, cfg) -> int:
    carovnik.run(cfg.config_path, get_stores(), reconfigure=cfg.config_path.exists())
    if args.first_run:
        carovnik.offer_first_run(cfg.root)
    return 0


def cmd_schedule(args, cfg) -> int:
    if args.action == "namesti":
        if urnik.is_manual(cfg.schedule):
            print("V nastavitve.yaml piše urnik: ročno, torej ni česa namestiti.")
            print("Vpiši uro (npr. 'dnevno 06:00') in poženi to znova.")
            return 1
        oncalendars = urnik.install(cfg.root, cfg.schedule, cfg.config_path)
        print(f"Nameščeno: zagon {cfg.schedule}  "
              f"(systemd OnCalendar={', '.join(oncalendars)})")
        print("Uro spremeni v nastavitve.yaml, nato poženi to znova.")
    elif args.action == "odstrani":
        urnik.remove()
        print("Časovnik odstranjen.")
    else:
        print(urnik.status())
    return 0


def _date(value: str | None):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


class SlovenskaPomoc(argparse.HelpFormatter):

    def add_usage(self, usage, actions, groups, prefix="uporaba: "):
        super().add_usage(usage, actions, groups, prefix)


def _po_slovensko(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser._positionals.title = "ukazi"
    parser._optionals.title = "možnosti"
    return parser


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-h", "--pomoc", action="help", default=argparse.SUPPRESS,
                        help="izpiši to pomoč in končaj")
    common.add_argument("--nastavitve", dest="config", metavar="POT",
                        default=argparse.SUPPRESS, help="pot do nastavitve.yaml")
    common.add_argument("-p", "--podrobno", dest="verbose", action="store_true",
                        default=argparse.SUPPRESS, help="izpiši vsako zahtevo in odločitev")

    parser = _po_slovensko(argparse.ArgumentParser(
        prog="letaki", description="Arhiv slovenskih trgovinskih katalogov",
        parents=[common], add_help=False, formatter_class=SlovenskaPomoc))
    sub = parser.add_subparsers(dest="command")

    def podukaz(name: str, help_text: str) -> argparse.ArgumentParser:
        return _po_slovensko(sub.add_parser(
            name, parents=[common], add_help=False,
            formatter_class=SlovenskaPomoc, help=help_text))

    run = podukaz("prenesi", "prenese vse novo (privzeto)")
    run.add_argument("--trgovina", action="append", dest="stores", metavar="IME",
                     help="samo ta trgovina")
    run.add_argument("--poskusno", dest="dry_run", action="store_true",
                     help="pokaži, kaj je novega, ne prenašaj")
    run.add_argument("--vse", dest="all", action="store_true",
                     help="skupaj s tematskimi brošurami")
    run.add_argument("--brez-mesa", dest="no_meat", action="store_true",
                     help="brez kopij samo z mesnimi stranmi")
    run.set_defaults(func=cmd_run)

    listing = podukaz("seznam", "kaj je v arhivu")
    listing.set_defaults(func=cmd_list)

    meat = podukaz("meso", "zgradi kopije katalogov samo z mesnimi stranmi")
    meat.add_argument("--trgovina", action="append", dest="stores", metavar="IME")
    meat.add_argument("--znova", dest="rebuild", action="store_true",
                      help="naredi obstoječe kopije na novo")
    meat.set_defaults(func=cmd_meat)

    audit = podukaz("pregled", "poišči datoteke v arhivu, ki jih izbor ne bi zbral")
    audit.add_argument("--izbrisi", dest="purge", action="store_true", help="izbriši jih")
    audit.set_defaults(func=cmd_audit)

    sched = podukaz("urnik", "namesti ali odstrani samodejni časovnik")
    sched.add_argument("action", nargs="?", default="stanje",
                       choices=["namesti", "odstrani", "stanje"])
    sched.set_defaults(func=cmd_schedule)

    setup = podukaz("nastavitev", "vprašanja, ki napišejo nastavitve.yaml in namestijo časovnik")
    setup.add_argument("--brez-prvega-zagona", dest="first_run", action="store_false",
                       help="ne ponudi takojšnjega prenosa")
    setup.set_defaults(func=cmd_setup, first_run=True)

    argv = sys.argv[1:]
    if not any(arg in sub.choices for arg in argv) \
            and any(arg.split("=")[0] in RUN_FLAGS for arg in argv):
        argv = ["prenesi", *argv]
    args = parser.parse_args(argv)
    config_path = getattr(args, "config", None)
    verbose = getattr(args, "verbose", False)

    cfg = nastavitve_modul.load(config_path)

    if not cfg.config_path.exists() and args.command != "nastavitev" and sys.stdin.isatty():
        carovnik.run(cfg.config_path, get_stores(), reconfigure=False)
        cfg = nastavitve_modul.load(config_path)

    dnevnik.setup(cfg.log_dir, verbose)
    if args.command is None:
        return cmd_home(cfg)
    return args.func(args, cfg)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nUstavljeno. Nič napol prenesenega ne ostane; poženi znova za naprej.")
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
