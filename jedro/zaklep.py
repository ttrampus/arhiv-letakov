from __future__ import annotations

import logging
import os
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None

log = logging.getLogger(__name__)

# Windows zaklene območje bajtov, ki ga drugi proces ne more niti prebrati;
# zaklenemo bajt daleč za vsebino, da PID ostane berljiv.
ZAKLENJEN_BAJT = 1 << 30


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

    def _zakleni(self) -> bool:
        try:
            if fcntl is not None:
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                self._fh.seek(ZAKLENJEN_BAJT)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _odkleni(self) -> None:
        try:
            if fcntl is not None:
                fcntl.flock(self._fh, fcntl.LOCK_UN)
            else:
                self._fh.seek(ZAKLENJEN_BAJT)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            log.debug("zaklepa ni bilo mogoče sprostiti", exc_info=True)

    def __enter__(self) -> "Zaklep":
        if fcntl is None and msvcrt is None:
            log.warning("ta sistem ne zna zakleniti datoteke; hkratnih zagonov "
                        "ne morem preprečiti")
            return self

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+b")
        if not self._zakleni():
            self._fh.seek(0)
            holder = self._fh.read(32).decode("ascii", "replace").strip() or "neznan"
            self._fh.close()
            self._fh = None
            raise Zaseden(f"drug zagon že teče (PID {holder}), tega preskočim")

        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os.getpid()).encode("ascii"))
        self._fh.flush()
        return self

    def __exit__(self, *exc_info) -> None:
        if self._fh is None:
            return
        try:
            self._odkleni()
        finally:
            self._fh.close()
            self._fh = None
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                log.debug("datoteke zaklepa ni bilo mogoče pobrisati", exc_info=True)
