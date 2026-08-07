from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"

_IMENA = {"WARNING": "opozorilo", "ERROR": "napaka", "CRITICAL": "huda napaka"}


class ConsoleFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        if record.exc_info:
            return super().format(record)
        message = record.getMessage()
        if record.levelno >= logging.WARNING:
            return f"{_IMENA.get(record.levelname, record.levelname.lower())}: {message}"
        return message


def setup(log_dir: Path, verbose: bool = False) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.raiseExceptions = False

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_FORMAT) if verbose else ConsoleFormatter())
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "arhiv-letakov.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(file_handler)

    for noisy in ("urllib3", "PIL", "img2pdf"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
