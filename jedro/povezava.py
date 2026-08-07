from __future__ import annotations

import logging
import time
from typing import Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .nastavitve import Config

log = logging.getLogger(__name__)


class HttpFetcher:
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
        retry = Retry(total=config.max_retries, backoff_factor=1.5,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET", "HEAD"]))
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _throttle(self) -> None:
        wait = self.config.delay_between_requests - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str, *, stream: bool = False, **kwargs) -> requests.Response:
        self._throttle()
        timeout = self.config.download_timeout if stream else self.config.request_timeout
        log.debug("GET %s", url)
        response = self.session.get(url, timeout=timeout, stream=stream, **kwargs)
        response.raise_for_status()
        return response

    def get_html(self, url: str) -> str:
        return self.get(url).text

    def close(self) -> None:
        self.session.close()


class BrowserFetcher:

    def __init__(self, config: Config):
        self.config = config
        self._playwright = None
        self._browser = None
        self._context = None

    def _context_or_start(self):
        if self._context is not None:
            return self._context
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright manjka. Poženi ./namesti.sh ali: "
                               "pip install playwright && playwright install chromium") from exc

        log.info("Zaganjam Chromium brez okna")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.config.browser_headless)
        self._context = self._browser.new_context(
            user_agent=self.config.user_agent,
            locale="sl-SI",
            viewport={"width": 1440, "height": 1000},
            extra_http_headers={"Accept-Language": "sl-SI,sl;q=0.9,en;q=0.8"})
        self._context.set_default_timeout(self.config.browser_timeout)
        return self._context

    def get_html(self, url: str, wait_for: str | None = None, settle_ms: int = 2500) -> str:
        page = self._context_or_start().new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            if wait_for:
                page.wait_for_selector(wait_for, state="attached")
            else:
                try:
                    page.wait_for_load_state("networkidle")
                except Exception:
                    pass
            page.wait_for_timeout(settle_ms)
            return page.content()
        finally:
            page.close()

    def capture(self, url: str, predicate: Callable[[str], bool], *,
                scroll: bool = True, settle_ms: int = 4000) -> tuple[str, list[str]]:
        page = self._context_or_start().new_page()
        seen: list[str] = []

        def on_response(response):
            if predicate(response.url) and response.url not in seen:
                seen.append(response.url)

        page.on("response", on_response)
        try:
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle")
            except Exception:
                pass
            if scroll:
                for _ in range(12):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(400)
            page.wait_for_timeout(settle_ms)
            return page.content(), seen
        finally:
            page.remove_listener("response", on_response)
            page.close()

    def capture_request_header(self, url: str, url_contains: str, header: str,
                               settle_ms: int = 4000) -> str | None:
        page = self._context_or_start().new_page()
        found: list[str] = []

        def on_request(request):
            if url_contains in request.url and not found:
                value = request.headers.get(header.lower())
                if value:
                    found.append(value)

        page.on("request", on_request)
        try:
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle")
            except Exception:
                pass
            page.wait_for_timeout(settle_ms)
            return found[0] if found else None
        finally:
            page.remove_listener("request", on_request)
            page.close()

    def api_get(self, url: str, headers: dict[str, str] | None = None):
        response = self._context_or_start().request.get(
            url, headers={"Accept": "application/json", **(headers or {})},
            timeout=self.config.browser_timeout)
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status} pri branju {url}")
        return response.json()

    def download(self, url: str, referer: str | None = None) -> bytes:
        response = self._context_or_start().request.get(
            url, headers={"Referer": referer} if referer else None,
            timeout=self.config.browser_timeout)
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status} pri branju {url}")
        return response.body()

    def close(self) -> None:
        for resource in (self._context, self._browser, self._playwright):
            if resource is None:
                continue
            try:
                resource.close() if resource is not self._playwright else resource.stop()
            except Exception:
                log.debug("napaka pri zapiranju vira brskalnika", exc_info=True)
        self._playwright = self._browser = self._context = None


class Fetchers:

    def __init__(self, config: Config):
        self.config = config
        self.http = HttpFetcher(config)
        self._browser: BrowserFetcher | None = None

    @property
    def browser(self) -> BrowserFetcher:
        if self._browser is None:
            self._browser = BrowserFetcher(self.config)
        return self._browser

    def close(self) -> None:
        self.http.close()
        if self._browser is not None:
            self._browser.close()
