from __future__ import annotations

import re
from datetime import date

_DATE = re.compile(r"(\d{1,2})\s*\.\s*(\d{1,2})\s*\.(?:\s*(\d{4}))?")
_SEPARATORS = re.compile(r"\s*(?:-|–|—|do|to)\s*", re.IGNORECASE)

_MONTH_NAMES = {
    "januar": 1, "februar": 2, "marec": 3, "marca": 3, "april": 4, "maj": 5,
    "junij": 6, "julij": 7, "avgust": 8, "september": 9, "oktober": 10,
    "oktobra": 10, "november": 11, "december": 12,
}
_MONTH_TEXT = re.compile(
    r"\b(" + "|".join(sorted(_MONTH_NAMES, key=len, reverse=True)) + r")[a-z]*\s+(\d{4})\b",
    re.IGNORECASE)


def parse_range(text: str | None) -> tuple[date | None, date | None]:
    if not text:
        return None, None

    matches = _DATE.findall(text)
    if not matches:
        return _parse_month_name(text), None

    years = [int(y) for _, _, y in matches if y]
    fallback_year = years[-1] if years else date.today().year

    parsed = []
    for day, month, year in matches[:2]:
        try:
            parsed.append(date(int(year) if year else fallback_year, int(month), int(day)))
        except ValueError:
            continue

    if not parsed:
        return None, None
    if len(parsed) == 1:
        return parsed[0], None

    start, end = parsed[0], parsed[1]
    if end < start and not matches[0][2]:
        try:
            start = start.replace(year=start.year - 1)
        except ValueError:
            pass
    return start, end


def _parse_month_name(text: str) -> date | None:
    match = _MONTH_TEXT.search(text)
    if not match:
        return None
    month = _MONTH_NAMES.get(match.group(1).lower())
    if not month:
        return None
    try:
        return date(int(match.group(2)), month, 1)
    except ValueError:
        return None


def looks_like_range(text: str) -> bool:
    return bool(_DATE.search(text) and _SEPARATORS.search(text))
