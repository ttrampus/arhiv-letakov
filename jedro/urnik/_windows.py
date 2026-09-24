"""Opravilo v Task Schedulerju.

Registrira ga namesti-windows.ps1 (Register-ScheduledTask), ker schtasks.exe
za gMSA ne da dostopa do omrežja, geslo računa pa bi rabil v ukazni vrstici.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ._razbiranje import _razberi

OPRAVILO = "arhiv-letakov"
MAPA_OPRAVIL = "\\arhiv-letakov\\"

DNEVI_POWERSHELL = {"pon": "Monday", "tor": "Tuesday", "sre": "Wednesday",
                    "cet": "Thursday", "čet": "Thursday", "pet": "Friday",
                    "sob": "Saturday", "ned": "Sunday"}


def sprozilci(schedule: str) -> list[dict]:
    """Urnik kot seznam sprožilcev za namesti-windows.ps1."""
    days, times = _razberi(schedule)
    return [{"dnevi": [DNEVI_POWERSHELL[d] for d in days],
             "ura": f"{int(hour):02d}:{minute}"}
            for hour, minute in times]


def ukaz_programa(project_dir: Path, config_path: Path | None = None) -> tuple[str, str]:
    """Program in argumenti za opravilo; pot do nastavitev gre vedno zraven."""
    if getattr(sys, "frozen", False):
        program = str(Path(sys.executable).resolve())
        argumenti = []
    else:
        program = str(Path(sys.executable).resolve())
        argumenti = [f'"{project_dir / "letaki.py"}"']
    nastavitve = config_path or project_dir / "nastavitve.yaml"
    argumenti += ["--nastavitve", f'"{nastavitve}"', "prenesi"]
    return program, " ".join(argumenti)


def _schtasks() -> str:
    """Absolutna pot, da podtaknjen schtasks.exe v trenutni mapi ne steče."""
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "schtasks.exe")


def _zazeni(args: list[str]) -> subprocess.CompletedProcess:
    # schtasks piše v kodni strani OEM (852 pri slovenskih nastavitvah).
    return subprocess.run([_schtasks(), *args], capture_output=True, text=True,
                          encoding="oem", errors="replace")


def install(project_dir: Path, schedule: str, config_path: Path | None = None) -> list[str]:
    raise RuntimeError(
        "Na Windows opravilo registrira namesti-windows.ps1, ki nastavi servisni "
        "račun, pravice in omejitve. Poženi:  .\\namesti-windows.ps1 -Arhiv "
        "\\\\streznik\\delnica\\letaki -Racun DOMENA\\racun$")


def remove() -> None:
    _zazeni(["/Delete", "/F", "/TN", MAPA_OPRAVIL + OPRAVILO])


def installed() -> bool:
    return _zazeni(["/Query", "/TN", MAPA_OPRAVIL + OPRAVILO]).returncode == 0


def scope() -> str:
    return "opravilo Task Schedulerja"


def status() -> str:
    if not installed():
        return "Opravilo ni nameščeno. Namesti ga z namesti-windows.ps1."
    result = _zazeni(["/Query", "/TN", MAPA_OPRAVIL + OPRAVILO,
                      "/V", "/FO", "LIST"])
    return (result.stdout + result.stderr).strip()
