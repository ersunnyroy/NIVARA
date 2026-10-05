"""Zerodha Kite Connect v3 REST adapter for live quotes and per-symbol daily history.

UNTESTED AGAINST THE LIVE API: written from Kite Connect's public documentation without credentials.
Validate with a real api_key/access_token before relying on it. Credentials are never logged.
EOD market-wide data (securities/bhavcopy/indices) comes from NSE, not from this adapter.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, date, datetime
from typing import Any

import httpx

from app.config.settings import get_settings
from app.data.brokers.upstox import _parse_ts
from app.data.nse.parsers import num
from app.data.providers.base import DataUnavailable, MarketDataProvider, NotConfigured
from app.data.rss import IST
from app.data.types import DailyBar, DataQuality, Provenance, ProviderResult, Quote

logger = logging.getLogger(__name__)

BASE_URL = "https://api.kite.trade"


class KiteProvider(MarketDataProvider):
    """Quotes (``/quote?i=NSE:SYMBOL``) and daily history (``/instruments/historical/{token}/day``)."""

    name = "kite"

    def __init__(
        self,
        api_key: str | None = None,
        access_token: str | None = None,
        *,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        s = get_settings()
        self._api_key = api_key if api_key is not None else s.kite_api_key
        self._token = access_token if access_token is not None else s.kite_access_token
        self._http = client or httpx.Client(timeout=timeout)
        self._tokens: dict[str, int] | None = None

    def _headers(self) -> dict[str, str]:
        if not self._api_key or not self._token:
            raise NotConfigured("Kite api key / access token not configured (KITE_API_KEY, KITE_ACCESS_TOKEN)")
        return {"X-Kite-Version": "3", "Authorization": f"token {self._api_key}:{self._token}"}

    def _get(self, url: str, params: Any = None) -> httpx.Response:
        headers = self._headers()
        try:
            resp = self._http.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise DataUnavailable(f"Kite request failed: {type(exc).__name__}") from exc
        if resp.status_code in (401, 403):
            raise NotConfigured(f"Kite rejected credentials (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise DataUnavailable(f"Kite HTTP {resp.status_code}")
        return resp

    def _json(self, url: str, params: Any = None) -> dict[str, Any]:
        body = self._get(url, params).json()
        if body.get("status") != "success":
            raise DataUnavailable(f"Kite error: {body.get('error_type') or body.get('status')}")
        return body

    # -------------------------------------------------------------- ABC
    def securities(self) -> ProviderResult:
        raise NotConfigured("EOD securities come from NSE")

    def daily_bars(self, session: date) -> ProviderResult:
        raise NotConfigured("EOD bhavcopy comes from NSE")

    def index_bars(self, session: date) -> ProviderResult:
        raise NotConfigured("EOD index data comes from NSE")

    def quotes(self, symbols: list[str]) -> ProviderResult:
        if not symbols:
            raise DataUnavailable("no symbols requested")
        url = f"{BASE_URL}/quote"
        body = self._json(url, [("i", f"NSE:{s.upper()}") for s in symbols])
        retrieved = datetime.now(UTC)
        out: list[Quote] = []
        warnings: list[str] = []
        for key, item in (body.get("data") or {}).items():
            sym = key.split(":", 1)[-1]
            ltp = num(item.get("last_price"))
            if ltp is None:
                continue
            ohlc = item.get("ohlc") or {}
            ts = _parse_ts(item.get("last_trade_time")) or _parse_ts(item.get("timestamp"))
            if ts is None:
                warnings.append(f"{sym}: no exchange timestamp; using retrieval time")
            vol = num(item.get("volume"))
            out.append(
                Quote(
                    symbol=sym, ts=ts or retrieved, ltp=ltp, open=num(ohlc.get("open")), high=num(ohlc.get("high")),
                    low=num(ohlc.get("low")), prev_close=num(ohlc.get("close")),  # Kite ohlc.close = previous close
                    volume=int(vol) if vol is not None else None, vwap=num(item.get("average_price")),
                    is_delayed=False,
                )
            )
        missing = {s.upper() for s in symbols} - {q.symbol for q in out}
        warnings += [f"no quote for {s}" for s in sorted(missing)]
        prov = Provenance("Kite Connect quote (v3)", retrieved, max((q.ts for q in out), default=None), url,
                          DataQuality.UNVERIFIED)
        return ProviderResult(out, prov, warnings)

    def _instrument_token(self, symbol: str) -> int | None:
        if self._tokens is None:
            text = self._get(f"{BASE_URL}/instruments/NSE").text
            self._tokens = {
                r["tradingsymbol"]: int(r["instrument_token"])
                for r in csv.DictReader(io.StringIO(text))
                if r.get("segment") == "NSE" and r.get("instrument_token", "").isdigit()
            }
        return self._tokens.get(symbol.upper())

    def history(self, symbol: str, start: date, end: date) -> ProviderResult:
        token = self._instrument_token(symbol)
        if token is None:
            raise DataUnavailable(f"Kite instrument token not found for {symbol}")
        url = f"{BASE_URL}/instruments/historical/{token}/day"
        body = self._json(url, {"from": start.isoformat(), "to": end.isoformat()})
        bars: list[DailyBar] = []
        for c in (body.get("data") or {}).get("candles") or []:
            if len(c) < 6:
                continue
            ts = _parse_ts(str(c[0]).replace("+0530", "+05:30"))
            o, h, lo, cl, v = (num(x) for x in c[1:6])
            if ts is None or None in (o, h, lo, cl, v):
                continue
            bars.append(DailyBar(symbol.upper(), None, ts.astimezone(IST).date(), o, h, lo, cl, None, int(v)))  # type: ignore[arg-type]
        bars.sort(key=lambda b: b.date)
        prov = Provenance("Kite Connect historical candles (v3)", datetime.now(UTC), None, url, DataQuality.UNVERIFIED)
        return ProviderResult(bars, prov)
