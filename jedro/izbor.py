from __future__ import annotations

import re

from .modeli import Magazine

DEFAULT_DENY = [
    "šola", "sola", "šolske", "solske", "potrebščine", "potrebscine",
    "zlatarna", "poroka", "nakit",
    "ferdo", "otroci", "tačke", "tacke",
    "vinski", "vino",
    "kuharija", "recept", "knjižica", "knjizica",
    "trajnostni", "party box",
    "sladoled", "zaščita kože", "zascita koze", "sonc",
    "amo essere", "brošura", "brosura",
    "mojih 10", "pika zgibanka",
    "radi imamo domače", "radi imamo domace",
    "tehnika", "multimedija", "moda", "vrt", "tekstil",
]

DEFAULT_ALLOW = [
    "redni katalog", "akcijski katalog", "letak",
    "lidlov katalog", "online katalog", "best offer",
    "interspar", "despar",
]

WEEKLY_NUMBERING = re.compile(r"katalog\s*\d{1,2}\s*/\s*\d{2}", re.IGNORECASE)

DEFAULT_MAX_DAYS = 21


def is_weekly_food_flyer(magazine: Magazine, max_days: int = DEFAULT_MAX_DAYS,
                         deny: list[str] | None = None,
                         allow: list[str] | None = None) -> tuple[bool, str]:
    title = magazine.title.lower()

    for word in deny if deny is not None else DEFAULT_DENY:
        if word.lower() in title:
            return False, f"tematski naslov ({word})"

    for word in allow if allow is not None else DEFAULT_ALLOW:
        if word.lower() in title:
            return True, "naslov tedenskega letaka"

    if WEEKLY_NUMBERING.search(title):
        return True, "tedenska oštevilčenost"

    days = validity_days(magazine)
    if days is None:
        return True, "brez datumov in brez ujemanja besed"
    if days <= max_days:
        return True, f"veljavnost {days} dni"
    return False, f"veljavnost {days} dni (več kot {max_days})"


def validity_days(magazine: Magazine) -> int | None:
    if not magazine.date_from or not magazine.date_to:
        return None
    return (magazine.date_to - magazine.date_from).days
