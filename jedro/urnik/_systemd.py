"""Časovnik systemd za Linux strežnike."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ._razbiranje import to_oncalendar

UNIT_DIR = Path.home() / ".config/systemd/user"
SYSTEM_UNIT_DIR = Path("/etc/systemd/system")
SERVICE = "arhiv-letakov.service"
TIMER = "arhiv-letakov.timer"


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
