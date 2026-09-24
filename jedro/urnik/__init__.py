"""Urnik zagona: Task Scheduler na Windows, sicer systemd."""

from __future__ import annotations

import os

from ._razbiranje import (CRON_DNEVI, DNEVI, ROCNO, describe, is_manual,
                          to_cron, to_oncalendar)

if os.name == "nt":
    from . import _windows as _sistem
else:
    from . import _systemd as _sistem

install = _sistem.install
remove = _sistem.remove
installed = _sistem.installed
scope = _sistem.scope
status = _sistem.status

__all__ = ["CRON_DNEVI", "DNEVI", "ROCNO", "describe", "install", "installed",
           "is_manual", "remove", "scope", "status", "to_cron", "to_oncalendar"]
