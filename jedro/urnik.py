from __future__ import annotations

import re
import subprocess
from pathlib import Path

UNIT_DIR = Path.home() / ".config/systemd/user"
SERVICE = "arhiv-letakov.service"
TIMER = "arhiv-letakov.timer"

DNEVI = {"pon": "Mon", "tor": "Tue", "sre": "Wed", "cet": "Thu", "čet": "Thu",
         "pet": "Fri", "sob": "Sat", "ned": "Sun"}

ROCNO = ("rocno", "ročno", "nikoli", "brez")


def is_manual(schedule: str) -> bool:
    return schedule.strip().lower() in ROCNO


def to_oncalendar(schedule: str) -> list[str]:
    text = schedule.strip()
    times = re.findall(r"(\d{1,2}):(\d{2})", text)
    first = re.search(r"\d{1,2}:\d{2}", text)

    when = (text[:first.start()] if first else text).strip().lower().rstrip(",")
    if not when or when == "dnevno":
        day_part = "*-*-*"
    elif when == "tedensko":
        day_part = "Thu"
    else:
        days = [DNEVI[d.strip()[:3]] for d in when.split(",") if d.strip()[:3] in DNEVI]
        day_part = ",".join(days) if days else "*-*-*"

    if not times:
        times = [("06", "00")]
    return [f"{day_part} {int(h):02d}:{m}:00" for h, m in times]


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

    _systemctl("daemon-reload")
    _systemctl("enable", "--now", TIMER)
    subprocess.run(["loginctl", "enable-linger"], capture_output=True)
    return oncalendars


def remove() -> None:
    _systemctl("disable", "--now", TIMER)
    for unit in (SERVICE, TIMER):
        (UNIT_DIR / unit).unlink(missing_ok=True)
    _systemctl("daemon-reload")


def installed() -> bool:
    return (UNIT_DIR / TIMER).exists()


def status() -> str:
    if not installed():
        return "Časovnik ni nameščen. Poženi: ./letaki urnik namesti"
    listed = _systemctl("list-timers", "--all", TIMER, capture=True)
    logs = _systemctl("status", SERVICE, "--no-pager", "-n", "5", capture=True)
    return f"{listed}\n{logs}"


def _systemctl(*args: str, capture: bool = False) -> str:
    result = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)
    return (result.stdout + result.stderr).strip() if capture else ""
