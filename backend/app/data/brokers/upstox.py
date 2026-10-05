"""Upstox v2 REST adapter for live quotes and per-symbol daily history.

UNTESTED AGAINST THE LIVE API: written from Upstox's public v2 documentation without credentials.
Validate with a real access token before relying on it. Tokens are never logged.
EOD market-wide data (securities/bhavcopy/indices) comes from NSE, not from this adapter.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.config.settings import get_settings
from app.data.nse.parsers import num, parse_date
from app.data.providers.base import DataUnavailable, MarketDataProvider, NotConfigured
from app.data.rss import IST
from app.data.types import DailyBar, DataQuality, Provenance, ProviderResult, Quote

logger = logging.getLogger(__name__)

BASE_URL = "https://api.upstox.com/v2"


class UpstoxProvider(MarketDataProvider):
    """Quotes/history via Upstox. Symbols map to instrument keys ``NSE_EQ|<ISIN>``.

    Pass ``isin_by_symbol`` (e.g. from ``NSEMarketDataProvider.securities()``) or symbols already in
    instrument-key form (``NSE_EQ|INE002A01018``).
    """

    name = "upstox"

    def __init__(
        self,
        access_token: str | None = None,
        *,
        isin_by_symbol: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._token = access_token if access_token is not None else get_settings().upstox_access_token
        self.isin_by_symbol = dict(isin_by_symbol or {})
        self._http = client or httpx.Client(timeout=timeout)

    # -------------------------------------------------------------- helpers
    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise NotConfigured("Upstox access token not configured (UPSTOX_ACCESS_TOKEN)")
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def instrument_key(self, symbol: str) -> str | None:
        if "|" in symbol:
            return symbol
        isin = self.isin_by_symbol.get(symbol.upper())
        return f"NSE_EQ|{isin}" if isin else None

    def _get(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        headers = self._headers()
        try:
            resp = self._http.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise DataUnavailable(f"Upstox request failed: {type(exc).__name__}") from exc
        if resp.status_code in (401, 403):
            raise NotConfigured(f"Upstox rejected credentials (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise DataUnavailable(f"Upstox HTTP {resp.status_code}")
        body = resp.json()
        if body.get("status") != "success":
            raise DataUnavailable(f"Upstox error: {body.get('errors') or body.get('status')}")
        return body

    # -------------------------------------------------------------- ABC
    def securities(self) -> ProviderResult:
        raise NotConfigured("EOD securities come from NSE")

    def daily_bars(self, session: date) -> ProviderResult:
        raise NotConfigured("EOD bhavcopy comes from NSE")

    def index_bars(self, session: date) -> ProviderResult:
        raise NotConfigured("EOD index data comes from NSE")

    def quotes(self, symbols: list[str]) -> ProviderResult:
        keys: dict[str, str] = {}
        warnings: list[str] = []
        for s in symbols:
            k = self.instrument_key(s)
            if k:
                keys[k] = s
            else:
                warnings.append(f"no instrument key (ISIN) for {s}")
        if not keys:
            raise DataUnavailable("no resolvable instrument keys")
        url = f"{BASE_URL}/market-quote/quotes"
        body = self._get(url, {"instrument_key": ",".join(keys)})
        retrieved = datetime.now(UTC)
        out: list[Quote] = []
        for item in (body.get("data") or {}).values():
            sym = keys.get(item.get("instrument_token", "")) or item.get("symbol")
            ltp = num(item.get("last_price"))
            if not sym or ltp is None:
                continue
            ohlc = item.get("ohlc") or {}
            change = num(item.get("net_change"))
            ts = _parse_ts(item.get("last_trade_time")) or _parse_ts(item.get("timestamp"))
            if ts is None:
                warnings.append(f"{sym}: no exchange timestamp; using retrieval time")
            vol = num(item.get("volume"))
            out.append(
                Quote(
                    symbol=sym, ts=ts or retrieved, ltp=ltp, open=num(ohlc.get("open")), high=num(ohlc.get("high")),
                    low=num(ohlc.get("low")), prev_close=round(ltp - change, 4) if change is not None else None,
                    volume=int(vol) if vol is not None else None, vwap=num(item.get("average_price")),
                    is_delayed=False,
                )
            )
        prov = Provenance("Upstox market quote (v2)", retrieved, max((q.ts for q in out), default=None), url,
                          DataQuality.UNVERIFIED)
        return ProviderResult(out, prov, warnings)

    def history(self, symbol: str, start: date, end: date) -> ProviderResult:
        key = self.instrument_key(symbol)
        if not key:
            raise DataUnavailable(f"no instrument key (ISIN) for {symbol}")
        url = f"{BASE_URL}/historical-candle/{quote(key, safe='')}/day/{end.isoformat()}/{start.isoformat()}"
        body = self._get(url)
        bars: list[DailyBar] = []
        for c in (body.get("data") or {}).get("candles") or []:
            if len(c) < 6:
                continue
            ts = _parse_ts(c[0])
            o, h, lo, cl, v = (num(x) for x in c[1:6])
            if ts is None or None in (o, h, lo, cl, v):
                continue
            bars.append(DailyBar(symbol, None, ts.astimezone(IST).date(), o, h, lo, cl, None, int(v)))  # type: ignore[arg-type]
        bars.sort(key=lambda b: b.date)
        prov = Provenance("Upstox historical candles (v2)", datetime.now(UTC), None, url, DataQuality.UNVERIFIED)
        return ProviderResult(bars, prov)


def _parse_ts(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, int | float) or (isinstance(v, str) and v.isdigit()):
        x = float(v)
        return datetime.fromtimestamp(x / 1000 if x > 1e11 else x, UTC)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        d = parse_date(v)
        return datetime.combine(d, datetime.min.time(), IST) if d else None
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)
