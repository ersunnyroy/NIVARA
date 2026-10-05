"""Polite HTTP client for NSE endpoints (archives + www JSON API).

* Browser-like User-Agent, minimum interval between requests (thread-safe).
* Retries with exponential backoff on 5xx / timeouts / transport errors (never on 4xx).
* On-disk cache under ``settings.data_cache_dir/nse`` keyed by URL; ``ttl=None`` caches forever
  (immutable archive files for past sessions), otherwise the entry expires after ``ttl`` seconds.
* www.nseindia.com: 401/403 → prime cookies once via the home page and retry once.
* 404 (and other non-retryable 4xx) → ``DataUnavailable``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config.settings import Settings, get_settings
from app.data.providers.base import DataUnavailable, NotConfigured

logger = logging.getLogger(__name__)

WWW_HOST = "www.nseindia.com"
WWW_HOME = "https://www.nseindia.com/"


@dataclass(slots=True)
class FetchResult:
    url: str
    content: bytes
    retrieved_at: datetime  # when the bytes were fetched from upstream (cache file mtime on cache hits)
    from_cache: bool


class NSEClient:
    """Rate-limited, caching, retrying HTTP client for NSE. Inject ``transport``/``client`` in tests."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        cache_dir: Path | None = None,
        min_interval: float | None = None,
        max_retries: int = 3,
        backoff: float = 1.0,
        timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self.cache_dir = Path(cache_dir or Path(self.settings.data_cache_dir) / "nse")
        self.min_interval = self.settings.nse_min_request_interval_sec if min_interval is None else min_interval
        self.max_retries = max_retries
        self.backoff = backoff
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_request: float | None = None
        self._cookies_primed = False
        headers = {
            "User-Agent": self.settings.nse_user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if client is not None:
            self._http = client
            self._http.headers.update(headers)
        else:
            self._http = httpx.Client(
                headers=headers, timeout=timeout, follow_redirects=True, transport=transport
            )

    # ---------------------------------------------------------------- public
    def fetch(self, url: str, *, ttl: float | None = None, use_cache: bool = True) -> FetchResult:
        """GET ``url`` (bytes). ``ttl=None`` → cache forever; ``ttl<=0`` or ``use_cache=False`` → no cache read."""
        is_www = urlparse(url).hostname == WWW_HOST
        if not self.settings.nse_enabled:
            raise NotConfigured("NSE provider disabled (NSE_ENABLED=false)")
        if is_www and not self.settings.nse_website_api_enabled:
            raise NotConfigured("NSE website API disabled (NSE_WEBSITE_API_ENABLED=false)")

        path = self._cache_path(url)
        if use_cache and (ttl is None or ttl > 0):
            hit = self._read_cache(path, ttl)
            if hit is not None:
                content, mtime = hit
                logger.debug("nse cache hit %s", url)
                return FetchResult(url, content, mtime, True)

        content = self._get(url, is_www)
        now = datetime.now(UTC)
        if use_cache:
            self._write_cache(path, url, content)
        return FetchResult(url, content, now, False)

    def get_bytes(self, url: str, *, ttl: float | None = None) -> bytes:
        return self.fetch(url, ttl=ttl).content

    def get_json(self, url: str, *, ttl: float | None = 3600) -> Any:
        return json.loads(self.fetch(url, ttl=ttl).content)

    def invalidate(self, url: str) -> None:
        """Drop a cached entry (e.g. after the content failed to parse)."""
        self._cache_path(url).unlink(missing_ok=True)

    def close(self) -> None:
        self._http.close()

    # --------------------------------------------------------------- internals
    def _throttle(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last_request is not None:
                wait = self._last_request + self.min_interval - now
                if wait > 0:
                    self._sleep(wait)
            self._last_request = self._clock()

    def _request(self, url: str, is_www: bool) -> httpx.Response:
        headers = {"Referer": WWW_HOME} if is_www else None
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                self._sleep(self.backoff * 2 ** (attempt - 1))
            self._throttle()
            try:
                resp = self._http.get(url, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("nse request error %s (attempt %d): %s", url, attempt + 1, type(exc).__name__)
                continue
            if resp.status_code >= 500:
                last_exc = DataUnavailable(f"NSE returned HTTP {resp.status_code} for {url}")
                logger.warning("nse HTTP %d %s (attempt %d)", resp.status_code, url, attempt + 1)
                continue
            return resp
        raise DataUnavailable(f"NSE unreachable for {url}: {last_exc}") from last_exc

    def _prime_cookies(self) -> None:
        self._throttle()
        try:
            resp = self._http.get(WWW_HOME, headers={"Accept": "text/html,application/xhtml+xml"})
            logger.info("nse cookie priming: HTTP %d", resp.status_code)
        except httpx.HTTPError as exc:
            logger.warning("nse cookie priming failed: %s", type(exc).__name__)
        self._cookies_primed = True

    def _get(self, url: str, is_www: bool) -> bytes:
        resp = self._request(url, is_www)
        if is_www and resp.status_code in (401, 403):
            self._prime_cookies()
            resp = self._request(url, is_www)
        if resp.status_code == 404:
            raise DataUnavailable(f"Not found (404): {url}")
        if resp.status_code >= 400:
            raise DataUnavailable(f"NSE returned HTTP {resp.status_code} for {url}")
        return resp.content

    def _cache_path(self, url: str) -> Path:
        host = urlparse(url).hostname or "unknown"
        return self.cache_dir / host / hashlib.sha256(url.encode()).hexdigest()

    @staticmethod
    def _read_cache(path: Path, ttl: float | None) -> tuple[bytes, datetime] | None:
        try:
            st = path.stat()
        except FileNotFoundError:
            return None
        if ttl is not None and time.time() - st.st_mtime > ttl:
            return None
        try:
            return path.read_bytes(), datetime.fromtimestamp(st.st_mtime, UTC)
        except OSError:
            return None

    @staticmethod
    def _write_cache(path: Path, url: str, content: bytes) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.parent / f"{path.name}.tmp{os.getpid()}_{threading.get_ident()}"
            tmp.write_bytes(content)
            os.replace(tmp, path)
            (path.parent / f"{path.name}.url").write_text(url)
        except OSError as exc:
            logger.warning("nse cache write failed for %s: %s", url, exc)
