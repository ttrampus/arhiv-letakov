from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util.retry import Retry

from . import naslovi
from .nastavitve import Config

log = logging.getLogger(__name__)

KOS = 64 * 1024
CAS_POVEZAVE_S = 20

# Ne gredo naprej, ko preusmeritev vodi na drug gostitelj.
_OSEBNE_GLAVE = ("Authorization", "Cookie", "Proxy-Authorization")


class OmejitevPresezena(RuntimeError):
    """Odgovor je večji ali počasnejši, kot dovolijo meje v nastavitvah."""


class NapakaPosrednika(RuntimeError):
    """Posrednik zavrača povezavo; sporočilo pove, kaj narediti."""


def uporabi_sistemske_certifikate() -> bool:
    """TLS prek shrambe certifikatov sistema (CA podjetja pri prestrezanju TLS)."""
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    return True


class _PreverjenIP:
    """Zavrne povezavo, ki je kljub dovoljenemu imenu pristala na nejavnem naslovu.

    Preverja se odprta vtičnica, zato vmes DNS ne more ničesar zamenjati. Skozi
    posrednika je sogovornik posrednik, zato tam ne velja.
    """

    def _new_conn(self):
        sock = super()._new_conn()
        try:
            naslov = sock.getpeername()[0]
        except OSError:
            naslov = ""
        if not naslovi.je_javen_ip(naslov):
            sock.close()
            raise naslovi.ZavrnjenNaslov(
                f"{self.host} kaže na naslov, ki ni javen ({naslov or 'neznan'})")
        return sock


class _HTTPPovezava(_PreverjenIP, HTTPConnection):
    pass


class _HTTPSPovezava(_PreverjenIP, HTTPSConnection):
    pass


class _HTTPBazen(HTTPConnectionPool):
    ConnectionCls = _HTTPPovezava


class _HTTPSBazen(HTTPSConnectionPool):
    ConnectionCls = _HTTPSPovezava


class _Adapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"http": _HTTPBazen, "https": _HTTPSBazen}


class HttpFetcher:
    """Edina pot v splet: vsaka zahteva in preusmeritev gre skozi naslovi.preveri."""

    def __init__(self, config: Config):
        self.config = config
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sl-SI,sl;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        })
        # Brez Retry-After: strežnik bi z njim zadržal zajem poljubno dolgo.
        retry = Retry(total=config.max_retries, backoff_factor=1.5,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET", "HEAD"]),
                      respect_retry_after_header=False)
        adapter = _Adapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self._proxies = ({"http": config.proxy, "https": config.proxy}
                         if config.proxy else None)
        if config.proxy:
            log.info("promet teče skozi posrednika %s", config.proxy_za_izpis)

    def _throttle(self) -> None:
        wait = self.config.delay_between_requests - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def preveri(self, url: str, store: str | None) -> str:
        return naslovi.preveri(url, store, dodatni=self.config.extra_hosts,
                               dovoli_http=self.config.allow_http)

    def _poslji(self, metoda: str, url: str, **kwargs) -> requests.Response:
        if self._proxies is not None:
            kwargs.setdefault("proxies", self._proxies)
        try:
            return self.session.request(metoda, url, **kwargs)
        except requests.exceptions.ProxyError as exc:
            if "407" in str(exc):
                raise NapakaPosrednika(
                    "posrednik zahteva prijavo (407). Prijave NTLM/Kerberos na posredniku "
                    "program ne podpira; strežniku ali servisnemu računu dovolite prehod "
                    "brez prijave za gostitelje iz 'gostitelji' ali vpišite posrednika "
                    "z osnovno prijavo") from exc
            raise

    def get(self, url: str, *, store: str | None = None, stream: bool = False,
            **kwargs) -> requests.Response:
        """Brez stream=True je telo že prebrano (do meje), sicer ga bere klicatelj s kosi()."""
        target = self.preveri(url, store)
        kwargs.pop("allow_redirects", None)
        headers = dict(kwargs.pop("headers", None) or {})

        for _ in range(self.config.max_redirects + 1):
            self._throttle()
            log.debug("GET %s", target)
            response = self._poslji(
                "GET", target, headers=headers or None, stream=True,
                allow_redirects=False,
                timeout=(CAS_POVEZAVE_S, self.config.request_timeout), **kwargs)
            if not response.is_redirect:
                try:
                    response.raise_for_status()
                    if not stream:
                        self._preberi(response, target)
                except BaseException:
                    response.close()
                    raise
                return response

            location = response.headers.get("Location", "")
            response.close()
            naslednji = self.preveri(requests.compat.urljoin(target, location), store)
            if urlsplit(naslednji).netloc != urlsplit(target).netloc:
                headers = {k: v for k, v in headers.items()
                           if k.lower() not in {g.lower() for g in _OSEBNE_GLAVE}}
            target = naslednji
            kwargs.pop("params", None)

        raise requests.TooManyRedirects(
            f"več kot {self.config.max_redirects} preusmeritev pri {url}")

    def post(self, url: str, *, store: str | None = None, **kwargs) -> requests.Response:
        """POST na preverjen naslov; preusmeritvam pri POST ne sledimo."""
        target = self.preveri(url, store)
        self._throttle()
        log.debug("POST %s", target)
        response = self._poslji("POST", target, stream=True, allow_redirects=False,
                                timeout=(CAS_POVEZAVE_S, self.config.request_timeout),
                                **kwargs)
        try:
            response.raise_for_status()
            self._preberi(response, target)
        except BaseException:
            response.close()
            raise
        return response

    def kosi(self, response: requests.Response, limit_bytes: int, rok_s: float,
             opis: str):
        """Kosi telesa z mejo velikosti in skupnega trajanja celega prenosa."""
        napovedano = response.headers.get("Content-Length", "")
        if napovedano.isdigit() and int(napovedano) > limit_bytes:
            raise OmejitevPresezena(
                f"odgovor je napovedal {int(napovedano) / 1e6:.0f} MB, meja je "
                f"{limit_bytes / 1e6:.0f} MB: {opis}")
        rok = time.monotonic() + rok_s
        size = 0
        for chunk in response.iter_content(chunk_size=KOS):
            if not chunk:
                continue
            size += len(chunk)
            if size > limit_bytes:
                raise OmejitevPresezena(
                    f"prenos je presegel {limit_bytes / 1e6:.0f} MB: {opis}")
            if time.monotonic() > rok:
                raise OmejitevPresezena(f"prenos je trajal dlje od {rok_s:.0f} s: {opis}")
            yield chunk

    def _preberi(self, response: requests.Response, opis: str) -> None:
        limit = self.config.max_page_mb * 1_000_000
        response._content = b"".join(
            self.kosi(response, limit, self.config.request_timeout, opis))
        response._content_consumed = True

    def get_html(self, url: str, *, store: str | None = None) -> str:
        return self.get(url, store=store).text

    def close(self) -> None:
        self.session.close()


class Fetchers:
    def __init__(self, config: Config):
        self.config = config
        self.http = HttpFetcher(config)

    def close(self) -> None:
        self.http.close()
