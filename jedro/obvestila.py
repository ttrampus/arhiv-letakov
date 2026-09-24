from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)


def message(rows) -> str:
    lines = ["arhiv-letakov: zajem ne dela"]
    for row in rows:
        last_ok = (row["last_ok"] or "nikoli")[:10]
        reason = row["reason"] or "neznano"
        lines.append(f"{row['store']}: {row['failures']} zagonov zapored"
                     f" ({reason}), zadnjič uspelo {last_ok}")
    return "\n".join(lines)


def send(cfg, text: str) -> None:
    if cfg.notify_webhook:
        _webhook(cfg.notify_webhook, text, cfg.proxy)
    if cfg.notify_command:
        _command(cfg.notify_command, text)


def _webhook(url: str, text: str, proxy: str = "") -> None:
    try:
        import requests
        proxies = {"http": proxy, "https": proxy} if proxy else None
        response = requests.post(url, json={"text": text}, timeout=15, proxies=proxies)
        response.raise_for_status()
        log.info("obvestilo poslano na webhook")
    except Exception as exc:
        log.error("obvestila ni bilo mogoče poslati na webhook (%s)", exc)


def _command(command: str, text: str) -> None:
    # Ukaz piše skrbnik in sme biti cevovod; besedilo gre prek stdin, ne v ukaz.
    try:
        result = subprocess.run(command, shell=True, input=text, text=True,  # nosec B602
                                errors="replace", capture_output=True, timeout=60)
        if result.returncode:
            log.error("ukaz za obveščanje je vrnil %s: %s",
                      result.returncode, result.stderr.strip()[:200])
        else:
            log.info("obvestilo predano ukazu")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log.error("ukaza za obveščanje ni bilo mogoče pognati (%s)", exc)
