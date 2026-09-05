from __future__ import annotations

import logging
import os
from pathlib import Path

try:
    import fcntl
except ImportError:  # ne-POSIX sistemi: brez zaklepanja
    fcntl = None

log = logging.getLogger(__name__)


class Zaseden(RuntimeError):
    """Drug zagon že teče."""


class Zaklep:
    """Poskrbi, da dva zagona ne pišeta v isti arhiv in bazo hkrati.

    Časovnik zna sprožiti nov zajem, preden se prejšnji konča. Zaklep je
    datoteka ob bazi, ki jo tekoči zagon drži odprto.
    """

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def __enter__(self) -> "Zaklep":
        if fcntl is None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fh.seek(0)
            holder = self._fh.read().strip() or "neznan"
            self._fh.close()
            self._fh = None
            raise Zaseden(f"drug zagon že teče (PID {holder}), tega preskočim")
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os.getpid()))
        self._fh.flush()
        return self

    def __exit__(self, *exc_info) -> None:
        if self._fh is None:
            return
        try:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None
            self.path.unlink(missing_ok=True)
