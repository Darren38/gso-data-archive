"""Polite HTTP client for GSO PageMethods.

* One request at a time, with a minimum delay between requests.
* Retries only transient failures (timeouts, connection errors, 5xx, 429),
  with exponential backoff and jitter; honours Retry-After.
* Refuses to contact the real GSO host unless GSO_LIVE_ENABLED is set.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from .config import Settings

log = logging.getLogger(__name__)

LIVE_HOSTS = {"www.gso.org.my", "gso.org.my"}


class FetchError(Exception):
    error_type = "network_error"

    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


class HttpStatusError(FetchError):
    error_type = "http_error"


class LiveAccessDisabled(FetchError):
    error_type = "live_disabled"


@dataclass
class FetchResult:
    url: str
    status: int
    content: bytes
    content_type: str | None
    elapsed_ms: int


class GsoClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._last_request = 0.0
        self._warmed: set[str] = set()
        self._client = httpx.Client(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent, "Accept": "application/json, text/html;q=0.8"},
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GsoClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _check_allowed(self, url: str) -> None:
        host = (urlparse(url).hostname or "").lower()
        if host in LIVE_HOSTS and not self.settings.gso_live_enabled:
            raise LiveAccessDisabled(
                "live GSO access is disabled (set GSO_LIVE_ENABLED=true after reviewing "
                "GSO's terms of use — see docs/SOURCE_INVESTIGATION.md)"
            )

    def _throttle(self) -> None:
        wait = self.settings.request_delay_seconds - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    def _request(self, method: str, url: str, **kwargs) -> FetchResult:
        self._check_allowed(url)
        attempts = self.settings.max_retries + 1
        last_exc: FetchError | None = None
        for attempt in range(1, attempts + 1):
            self._throttle()
            started = time.monotonic()
            try:
                resp = self._client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = FetchError(f"{type(exc).__name__}: {exc}")
                retry_after = None
            else:
                self._last_request = time.monotonic()
                elapsed = int((time.monotonic() - started) * 1000)
                if resp.status_code < 400:
                    return FetchResult(url, resp.status_code, resp.content, resp.headers.get("content-type"), elapsed)
                last_exc = HttpStatusError(f"HTTP {resp.status_code} from {url}", resp.status_code)
                if resp.status_code != 429 and resp.status_code < 500:
                    raise last_exc  # 4xx other than 429 will not fix itself
                retry_after = resp.headers.get("retry-after")
            self._last_request = time.monotonic()
            if attempt == attempts:
                break
            delay = min(60.0, 2.0 ** attempt) + random.uniform(0, 1)
            if retry_after and retry_after.isdigit():
                delay = max(delay, min(300.0, float(retry_after)))
            log.warning("request failed (%s), retry %d/%d in %.1fs", last_exc, attempt, attempts - 1, delay)
            time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def warm_up(self, page_url: str) -> None:
        """GET the HTML page once per client so any session cookie is set, as a browser would."""
        if page_url in self._warmed:
            return
        try:
            self._request("GET", page_url)
        except LiveAccessDisabled:
            raise
        except FetchError as exc:
            log.info("warm-up GET %s failed (%s); continuing", page_url, exc)
        self._warmed.add(page_url)

    def post_pagemethod(self, url: str, body: dict | None, referer: str) -> FetchResult:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
        }
        return self._request("POST", url, json=body or {}, headers=headers)

    def get(self, url: str) -> FetchResult:
        return self._request("GET", url)
