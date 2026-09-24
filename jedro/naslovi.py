"""Seznam gostiteljev, ki jih program sme obiskati, in varen izpis naslovov.

Povezave do letakov pridejo s tujih strani, zato vsako preverimo, preden gre
program nanjo. Naslov IP same povezave preveri še povezava.py.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

# Pika spredaj pomeni tudi poddomene; samo za lastne domene trgovin. Skupne
# domene (iPaper, Publitas) so naštete natančno, sicer bi dovolili vse njihove stranke.
DOVOLJENI: dict[str, tuple[str, ...]] = {
    "mercator": ("mercator.si", ".mercator.si"),
    "tus": ("tus.si", ".tus.si"),
    "spar": ("spar.si", ".spar.si", "cdn.ipaper.io"),  # getPdf.ashx preusmeri na iPaper
    "leclerc": ("e-leclerc.si", ".e-leclerc.si"),
    "lidl": ("lidl.si", ".lidl.si",
             "endpoints.leaflets.schwarz", "assets.leaflets.schwarz"),
    "hofer": ("hofer.si", ".hofer.si", "view.publitas.com"),
    "eurospin": ("eurospin.si", ".eurospin.si", "digitalflyer.eurospin.it"),
}

# Kar program dejansko obišče; za požarne zidove, ki ne znajo imen z *.
ZA_POZARNI_ZID: tuple[str, ...] = (
    "www.mercator.si",
    "www.tus.si",
    "www.spar.si", "letak.spar.si", "cdn.ipaper.io",
    "www.e-leclerc.si",
    "www.lidl.si", "endpoints.leaflets.schwarz", "assets.leaflets.schwarz",
    "www.hofer.si", "letaki.hofer.si", "view.publitas.com",
    "www.eurospin.si", "digitalflyer.eurospin.it",
)

VSE_TRGOVINE = "*"

_IME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
_PRIVZETA_VRATA = {"https": 443, "http": 80}


class ZavrnjenNaslov(ValueError):
    """Naslov ni na seznamu dovoljenih ciljev."""


def gostitelji(store: str | None = None,
               dodatni: dict[str, list[str]] | None = None) -> tuple[str, ...]:
    """Dovoljeni gostitelji za eno trgovino ali za vse skupaj."""
    extra = dodatni or {}
    if store is None:
        imena = {h for hosts in DOVOLJENI.values() for h in hosts}
        imena.update(h for hosts in extra.values() for h in hosts)
    else:
        imena = set(DOVOLJENI.get(store, ()))
        imena.update(extra.get(store, ()))
        imena.update(extra.get(VSE_TRGOVINE, ()))
    return tuple(sorted(h.lower().rstrip(".") for h in imena if h and h.strip(".")))


def _gostitelj_ustreza(host: str, dovoljeni: tuple[str, ...]) -> bool:
    for vzorec in dovoljeni:
        if vzorec.startswith("."):
            # ".si" sam ne sme dovoliti cele vrhnje domene.
            if vzorec.count(".") >= 2 and host.endswith(vzorec) and len(host) > len(vzorec):
                return True
        elif host == vzorec:
            return True
    return False


def je_javen_ip(naslov: str) -> bool:
    try:
        ip = ipaddress.ip_address(naslov.strip("[]").split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _je_zaseben_ip(host: str) -> bool:
    return je_ip(host) and not je_javen_ip(host)


def je_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
    except ValueError:
        return False
    return True


def preveri(url: str, store: str | None = None, *,
            dodatni: dict[str, list[str]] | None = None,
            dovoli_http: bool = False) -> str:
    """Vrne preverjen naslov ali vrže ZavrnjenNaslov."""
    if not url or not url.strip():
        raise ZavrnjenNaslov("prazen naslov")
    url = url.strip()
    if any(ord(c) < 0x21 or c in "\\\x7f" for c in url):
        raise ZavrnjenNaslov(f"naslov vsebuje nedovoljene znake: {mask(url)!r}")

    try:
        deli = urlsplit(url)
        vrata = deli.port
    except ValueError as exc:
        raise ZavrnjenNaslov(f"neveljaven naslov ({exc})") from exc

    shema = deli.scheme.lower()
    if shema not in _PRIVZETA_VRATA:
        raise ZavrnjenNaslov(f"shema {shema or '(brez)'} ni dovoljena: {mask(url)}")
    if shema == "http" and not dovoli_http:
        raise ZavrnjenNaslov(f"http ni dovoljen, samo https: {mask(url)}")
    if "@" in deli.netloc:
        raise ZavrnjenNaslov("naslov vsebuje poverilnice")
    if vrata is not None and vrata != _PRIVZETA_VRATA[shema]:
        raise ZavrnjenNaslov(f"vrata {vrata} niso dovoljena: {mask(url)}")

    host = (deli.hostname or "").lower().rstrip(".")
    if not host:
        raise ZavrnjenNaslov(f"naslov brez gostitelja: {mask(url)}")
    if _je_zaseben_ip(host):
        raise ZavrnjenNaslov(f"naslov kaže v zasebno omrežje: {host}")
    if je_ip(host):
        raise ZavrnjenNaslov(f"naslov na goli IP ni dovoljen: {host}")
    if not _IME.match(host):
        raise ZavrnjenNaslov(f"neveljavno ime gostitelja: {host!r}")

    dovoljeni = gostitelji(store, dodatni)
    if not dovoljeni:
        raise ZavrnjenNaslov(f"za trgovino {store} ni seznama dovoljenih gostiteljev")
    if not _gostitelj_ustreza(host, dovoljeni):
        raise ZavrnjenNaslov(f"gostitelj {host} ni na seznamu trgovine {store}")
    # Sestavljen iz preverjenih delov: v omrežje gre natanko to, kar smo preverili.
    return urlunsplit((shema, deli.netloc.lower(), deli.path or "/", deli.query, ""))


def je_dovoljen(url: str, store: str | None = None, **kwargs) -> bool:
    try:
        preveri(url, store, **kwargs)
        return True
    except ZavrnjenNaslov:
        return False


_UPORABNISKI_DEL = re.compile(r"^((?:[a-zA-Z][a-zA-Z0-9+.-]*:)?//)?[^/?#\s]*@")


def mask(url: str | None) -> str:
    """Naslov brez uporabnika in gesla, za dnevnik (tudi zapis brez sheme)."""
    if not url:
        return ""
    return _UPORABNISKI_DEL.sub(lambda m: f"{m.group(1) or ''}***:***@", str(url), count=1)
