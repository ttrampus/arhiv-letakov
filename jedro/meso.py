from __future__ import annotations

import re
import unicodedata

STEMS = [
    "mesn", "suhomesnat", "narezk", "narezek", "pecenk", "pecenic",
    "svinjsk", "svinjin",
    "govej", "govedin", "govedi",
    "telet", "teletin", "junet", "junetin", "junec",
    "jagnjet", "jagnje", "ovcj",
    "piscan", "kokosj",
    "perutnin", "putk", "puran",
    "kunc", "kunec", "divjacin", "srnin", "jelenov", "konjsk",
    "raca", "race", "raco", "raci", "racke", "racji", "racja", "racje",
    "zrezek", "zrezk", "kotlet", "brzol", "krac", "rebrc", "rebra", "rebrca",
    "stegn", "vratovin", "plecet", "plece", "potrebusin",
    "mleto meso", "mleta govedina", "mletin",
    "jetr", "jetrn", "vamp",
    "klobas", "kranjsk", "hrenovk", "salam", "sunk", "prsut",
    "pancet", "slanin", "speh", "zasek", "pastet",
    "mortadel", "tlacenk", "krvavic", "budjol", "safalad",
    "cevapcic", "cevap", "pleskavic", "pljeskavic", "raznjic",
    "gyros", "kebab", "nugget", "burger", "hamburger", "hot dog", "hotdog",
    "dunajski", "pohan", "paniran", "sekljan", "carski",
    "perutnina ptuj", "celjske mesnine", "mesnine",
    "argeta", "gavrilovic", "kosaki",
]

EXACT = ["meso", "mesa", "mesu", "mesom", "mesi", "poli", "pivka", "kare"]

FISH = [
    "riba", "ribe", "ribj", "losos", "tuna", "tunin", "postrv", "orada",
    "brancin", "skus", "sardin", "sled", "skoljk", "skamp", "kozic",
    "lignj", "hobotnic", "morski sadez",
]


def fold(text: str) -> str:
    lowered = text.lower().replace("ć", "c").replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFKD", lowered)
                   if not unicodedata.combining(c))


def build_pattern(stems: list[str], exact: list[str] | None = None) -> re.Pattern:
    parts = [rf"\b{re.escape(s)}" for s in sorted({fold(s) for s in stems},
                                                  key=len, reverse=True)]
    parts += [rf"\b{re.escape(w)}\b" for w in sorted({fold(w) for w in exact or []},
                                                     key=len, reverse=True)]
    return re.compile("(" + "|".join(parts) + ")", re.IGNORECASE)


DEFAULT_PATTERN = build_pattern(STEMS, EXACT)


def find_meat(text: str, pattern: re.Pattern | None = None) -> list[str]:
    if not text:
        return []
    folded = fold(text)
    hits = []
    for match in (pattern or DEFAULT_PATTERN).finditer(folded):
        end = match.end()
        while end < len(folded) and (folded[end].isalnum() or folded[end] == "-"):
            end += 1
        word = folded[match.start():end]
        if word not in hits:
            hits.append(word)
    return hits


def page_has_meat(text: str, pattern: re.Pattern | None = None) -> tuple[bool, list[str]]:
    hits = find_meat(text, pattern)
    return bool(hits), hits
