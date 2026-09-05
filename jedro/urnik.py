from __future__ import annotations

import re
import subprocess
from pathlib import Path

UNIT_DIR = Path.home() / ".config/systemd/user"
SYSTEM_UNIT_DIR = Path("/etc/systemd/system")
SERVICE = "arhiv-letakov.service"
TIMER = "arhiv-letakov.timer"

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


def install(project_dir: Path, schedule: str, config_path: Path | None = None) -> list[str]:
    oncalendars = to_oncalendar(schedule)
    python = project_dir / "venv/bin/python"
    default_config = project_dir / "nastavitve.yaml"
    config_arg = ("" if config_path is None or config_path == default_config
                  else f" --nastavitve {config_path}")
    UNIT_DIR.mkdir(parents=True, exist_ok=True)

    (UNIT_DIR / SERVICE).write_text(f"""[Unit]
Description=Prenos slovenskih trgovinskih letakov
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={project_dir}
ExecStart={python} {project_dir}/letaki.py{config_arg} prenesi
TimeoutStartSec=7200
""")

    lines = "\n".join(f"OnCalendar={expression}" for expression in oncalendars)
    (UNIT_DIR / TIMER).write_text(f"""[Unit]
Description=Arhiv slovenskih trgovinskih letakov ({schedule})

[Timer]
{lines}
Persistent=true
RandomizedDelaySec=900

[Install]
WantedBy=timers.target
""")

    _systemctl("daemon-reload", user=True)
    _systemctl("enable", "--now", TIMER, user=True)
    subprocess.run(["loginctl", "enable-linger"], capture_output=True)
    return oncalendars


def remove() -> None:
    _systemctl("disable", "--now", TIMER, user=True)
    for unit in (SERVICE, TIMER):
        (UNIT_DIR / unit).unlink(missing_ok=True)
    _systemctl("daemon-reload", user=True)


def system_installed() -> bool:
    """Enota, ki jo na strežnik postavi namesti-streznik.sh."""
    return (SYSTEM_UNIT_DIR / TIMER).exists()


def installed() -> bool:
    return (UNIT_DIR / TIMER).exists() or system_installed()


def scope() -> str:
    return "sistemski" if system_installed() else "uporabniški"


def status() -> str:
    if not installed():
        return "Časovnik ni nameščen. Poženi: ./letaki urnik namesti"
    listed = _systemctl("list-timers", "--all", TIMER, capture=True)
    logs = _systemctl("status", SERVICE, "--no-pager", "-n", "5", capture=True)
    return f"{listed}\n{logs}"


def _systemctl(*args: str, capture: bool = False, user: bool | None = None) -> str:
    # install() in remove() delata z uporabniškimi enotami, status pa s tisto,
    # ki je res nameščena.
    if user is None:
        user = not system_installed()
    prefix = ["--user"] if user else []
    result = subprocess.run(["systemctl", *prefix, *args], capture_output=True, text=True)
    return (result.stdout + result.stderr).strip() if capture else ""
