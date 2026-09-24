"""Branje urnika iz nastavitev; oblika je skupna vsem sistemom."""

from __future__ import annotations

import re

DNEVI = {"pon": "Mon", "tor": "Tue", "sre": "Wed", "cet": "Thu", "čet": "Thu",
         "pet": "Fri", "sob": "Sat", "ned": "Sun"}

CRON_DNEVI = {"pon": "1", "tor": "2", "sre": "3", "cet": "4", "čet": "4",
              "pet": "5", "sob": "6", "ned": "0"}

ROCNO = ("rocno", "ročno", "nikoli", "brez")


def is_manual(schedule: str) -> bool:
    return schedule.strip().lower() in ROCNO


def _razberi(schedule: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Vrne (dnevi, ure). Prazni dnevi pomenijo vsak dan."""
    text = schedule.strip()
    times = re.findall(r"(\d{1,2}):(\d{2})", text)
    first = re.search(r"\d{1,2}:\d{2}", text)

    when = (text[:first.start()] if first else text).strip().lower().rstrip(",")
    if not when or when == "dnevno":
        days = []
    elif when == "tedensko":
        days = ["cet"]  # takrat izide največ letakov
    else:
        days = [d.strip()[:3] for d in when.split(",") if d.strip()[:3] in DNEVI]

    return days, times or [("06", "00")]


def to_oncalendar(schedule: str) -> list[str]:
    days, times = _razberi(schedule)
    day_part = ",".join(DNEVI[d] for d in days) if days else "*-*-*"
    return [f"{day_part} {int(h):02d}:{m}:00" for h, m in times]


def to_cron(schedule: str) -> list[str]:
    """Isti urnik za strežnike brez systemd; brez ukaza, samo časovni del."""
    days, times = _razberi(schedule)
    day_part = ",".join(CRON_DNEVI[d] for d in days) if days else "*"
    return [f"{int(m)} {int(h)} * * {day_part}" for h, m in times]


def describe(schedule: str) -> str:
    return ", ".join(to_oncalendar(schedule))


