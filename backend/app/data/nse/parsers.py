"""Pure parsers for NSE file/API formats (bytes/str in → ``app.data.types`` records out).

Conventions: header names are whitespace-stripped; blank / ``-`` / ``NA`` cells → ``None``; broadcast
times are timezone-aware IST. Parsers never invent values — unparseable required fields skip the row.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from app.data.rss import IST, parse_feed
from app.data.types import (
    Announcement,
    CorporateActionRecord,
    DailyBar,
    EventRecord,
    FinancialStatement,
    FlowRecord,
    FuturesRow,
    HolidayRecord,
    IndexBar,
    OptionRow,
    ResultFiling,
    SecurityInfo,
    ShareholdingRecord,
)

logger = logging.getLogger(__name__)

# Equity-like CM series kept from bhavcopies (main board, trade-for-trade, SME).
EQUITY_SERIES: frozenset[str] = frozenset({"EQ", "BE", "BZ", "SM", "ST", "SZ"})
_NULLS = {"", "-", "--", "NA", "N/A", "NIL", "NULL", "NONE"}


class ParseError(ValueError):
    """Upstream content did not match the expected format."""


# ------------------------------------------------------------------ primitives
def decode(data: bytes | str) -> str:
    if isinstance(data, str):
        return data
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def unzip_first(data: bytes, suffix: str = ".csv") -> bytes:
    """Return the first member ending with ``suffix`` from a zip; non-zip input is returned unchanged."""
    if not data.startswith(b"PK"):
        return data
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(suffix)] or zf.namelist()
            if not names:
                raise ParseError("empty zip archive")
            return zf.read(names[0])
    except zipfile.BadZipFile as exc:
        raise ParseError(f"bad zip archive: {exc}") from exc


def clean(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return None if s.upper() in _NULLS else s


def num(value: Any) -> float | None:
    s = clean(value)
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def integer(value: Any) -> int | None:
    f = num(value)
    return None if f is None else round(f)


_DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d%b%Y")
_DT_FORMATS = ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


def parse_date(value: Any) -> date | None:
    s = clean(value)
    if s is None:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=IST).date()  # %b is case-insensitive ("JUN")
        except ValueError:
            continue
    return None


def parse_ist_datetime(value: Any) -> datetime | None:
    s = clean(value)
    if s is None:
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def csv_rows(data: bytes | str) -> list[dict[str, str]]:
    """DictReader with stripped header names and values; empty header columns dropped."""
    text = decode(unzip_first(data) if isinstance(data, bytes) else data)
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return []
    rows: list[dict[str, str]] = []
    for raw in reader:
        if not any(c.strip() for c in raw):
            continue
        rows.append({h: (raw[i].strip() if i < len(raw) else "") for i, h in enumerate(header) if h})
    return rows


def _require(rows: list[dict[str, str]], cols: Iterable[str], what: str) -> None:
    if rows:
        missing = [c for c in cols if c not in rows[0]]
        if missing:
            raise ParseError(f"{what}: missing columns {missing}")


# ------------------------------------------------------------------ securities
def parse_equity_list(data: bytes | str) -> list[SecurityInfo]:
    """EQUITY_L.csv (header names carry leading spaces)."""
    rows = csv_rows(data)
    _require(rows, ["SYMBOL", "NAME OF COMPANY", "SERIES", "ISIN NUMBER"], "EQUITY_L")
    return [
        SecurityInfo(
            symbol=r["SYMBOL"],
            name=r["NAME OF COMPANY"],
            series=clean(r.get("SERIES")),
            isin=clean(r.get("ISIN NUMBER")),
            listing_date=parse_date(r.get("DATE OF LISTING")),
            face_value=num(r.get("FACE VALUE")),
        )
        for r in rows
        if clean(r.get("SYMBOL"))
    ]


def parse_index_constituents(data: bytes | str) -> list[SecurityInfo]:
    """Nifty Indices ``ind_nifty*list.csv``: Company Name, Industry, Symbol, Series, ISIN Code."""
    rows = csv_rows(data)
    _require(rows, ["Company Name", "Symbol"], "index constituents")
    return [
        SecurityInfo(
            symbol=r["Symbol"],
            name=r["Company Name"],
            series=clean(r.get("Series")),
            isin=clean(r.get("ISIN Code")),
            industry=clean(r.get("Industry")),
        )
        for r in rows
        if clean(r.get("Symbol"))
    ]


# ------------------------------------------------------------------ CM bhavcopy
def _bar(
    symbol: str, series: str | None, d: date | None, o: Any, h: Any, lo: Any, c: Any, pc: Any, vol: Any, **kw: Any
) -> DailyBar | None:
    vals = (num(o), num(h), num(lo), num(c))
    volume = integer(vol)
    if d is None or any(v is None for v in vals) or volume is None:
        return None
    return DailyBar(symbol, series, d, *vals, prev_close=num(pc), volume=volume, **kw)  # type: ignore[arg-type]


def parse_cm_bhavcopy_udiff(data: bytes | str, series: Iterable[str] | None = EQUITY_SERIES) -> list[DailyBar]:
    """UDiFF CM bhavcopy (from 2024-07-08). Keeps ``FinInstrmTp == STK`` and the given series (None = all)."""
    keep = set(series) if series is not None else None
    rows = csv_rows(data)
    _require(rows, ["TradDt", "TckrSymb", "SctySrs", "OpnPric", "ClsPric", "TtlTradgVol"], "UDiFF CM bhavcopy")
    out: list[DailyBar] = []
    for r in rows:
        if r.get("FinInstrmTp") != "STK" or (keep is not None and r.get("SctySrs") not in keep):
            continue
        bar = _bar(
            r["TckrSymb"], clean(r.get("SctySrs")), parse_date(r.get("TradDt")),
            r.get("OpnPric"), r.get("HghPric"), r.get("LwPric"), r.get("ClsPric"), r.get("PrvsClsgPric"),
            r.get("TtlTradgVol"),
            turnover=num(r.get("TtlTrfVal")), trades=integer(r.get("TtlNbOfTxsExctd")), isin=clean(r.get("ISIN")),
        )
        if bar:
            out.append(bar)
    return out


def parse_cm_bhavcopy_legacy(data: bytes | str, series: Iterable[str] | None = EQUITY_SERIES) -> list[DailyBar]:
    """Legacy ``cmDDMONYYYYbhav.csv`` (before 2024-07-08)."""
    keep = set(series) if series is not None else None
    rows = csv_rows(data)
    _require(rows, ["SYMBOL", "SERIES", "OPEN", "CLOSE", "TOTTRDQTY", "TIMESTAMP"], "legacy CM bhavcopy")
    out: list[DailyBar] = []
    for r in rows:
        if keep is not None and r.get("SERIES") not in keep:
            continue
        bar = _bar(
            r["SYMBOL"], clean(r.get("SERIES")), parse_date(r.get("TIMESTAMP")),
            r.get("OPEN"), r.get("HIGH"), r.get("LOW"), r.get("CLOSE"), r.get("PREVCLOSE"), r.get("TOTTRDQTY"),
            turnover=num(r.get("TOTTRDVAL")), trades=integer(r.get("TOTALTRADES")), isin=clean(r.get("ISIN")),
        )
        if bar:
            out.append(bar)
    return out


def parse_delivery(data: bytes | str) -> dict[tuple[str, str], tuple[int | None, float | None]]:
    """``sec_bhavdata_full_DDMMYYYY.csv`` → {(symbol, series): (deliv_qty, deliv_pct)}; '-' → None."""
    rows = csv_rows(data)
    _require(rows, ["SYMBOL", "SERIES", "DELIV_QTY", "DELIV_PER"], "sec_bhavdata_full")
    return {(r["SYMBOL"], r["SERIES"]): (integer(r.get("DELIV_QTY")), num(r.get("DELIV_PER"))) for r in rows}


def merge_delivery(bars: list[DailyBar], delivery: dict[tuple[str, str], tuple[int | None, float | None]]) -> int:
    """Attach delivery qty/% in place; returns the number of bars matched."""
    matched = 0
    for b in bars:
        hit = delivery.get((b.symbol, b.series or ""))
        if hit is not None:
            b.delivery_qty, b.delivery_pct = hit
            matched += 1
    return matched


# ------------------------------------------------------------------ indices
def parse_index_close(data: bytes | str) -> list[IndexBar]:
    """``ind_close_all_DDMMYYYY.csv`` (all NSE indices incl. India VIX). '-' → None."""
    rows = csv_rows(data)
    _require(rows, ["Index Name", "Index Date", "Closing Index Value"], "ind_close_all")
    out: list[IndexBar] = []
    for r in rows:
        d, close = parse_date(r.get("Index Date")), num(r.get("Closing Index Value"))
        if d is None or close is None:
            continue
        out.append(
            IndexBar(
                index_name=r["Index Name"], date=d,
                open=num(r.get("Open Index Value")), high=num(r.get("High Index Value")),
                low=num(r.get("Low Index Value")), close=close, change_pct=num(r.get("Change(%)")),
                volume=num(r.get("Volume")), turnover_cr=num(r.get("Turnover (Rs. Cr.)")),
                pe=num(r.get("P/E")), pb=num(r.get("P/B")), div_yield=num(r.get("Div Yield")),
            )
        )
    return out


# ------------------------------------------------------------------ F&O
def parse_fo_bhavcopy_udiff(data: bytes | str) -> tuple[list[FuturesRow], list[OptionRow]]:
    """UDiFF F&O bhavcopy: STF/IDF futures, STO/IDO options (OptnTp CE/PE)."""
    rows = csv_rows(data)
    _require(rows, ["FinInstrmTp", "TckrSymb", "XpryDt", "ClsPric", "OpnIntrst"], "UDiFF FO bhavcopy")
    futs: list[FuturesRow] = []
    opts: list[OptionRow] = []
    for r in rows:
        kind = r.get("FinInstrmTp")
        d, expiry = parse_date(r.get("TradDt")), parse_date(r.get("XpryDt"))
        if d is None or expiry is None:
            continue
        oi, coi, vol = integer(r.get("OpnIntrst")) or 0, integer(r.get("ChngInOpnIntrst")) or 0, integer(
            r.get("TtlTradgVol")
        ) or 0
        if kind in ("STF", "IDF"):
            close = num(r.get("ClsPric"))
            if close is None:
                continue
            futs.append(
                FuturesRow(
                    underlying=r["TckrSymb"], instrument=kind, date=d, expiry=expiry,
                    open=num(r.get("OpnPric")), high=num(r.get("HghPric")), low=num(r.get("LwPric")), close=close,
                    settle=num(r.get("SttlmPric")), underlying_price=num(r.get("UndrlygPric")),
                    oi=oi, change_oi=coi, volume=vol, lot_size=integer(r.get("NewBrdLotQty")),
                )
            )
        elif kind in ("STO", "IDO"):
            strike, otype = num(r.get("StrkPric")), clean(r.get("OptnTp"))
            if strike is None or otype not in ("CE", "PE"):
                continue
            opts.append(
                OptionRow(
                    underlying=r["TckrSymb"], instrument=kind, date=d, expiry=expiry, strike=strike,
                    option_type=otype, close=num(r.get("ClsPric")), settle=num(r.get("SttlmPric")),
                    underlying_price=num(r.get("UndrlygPric")), oi=oi, change_oi=coi, volume=vol,
                )
            )
    return futs, opts


def parse_lot_sizes(data: bytes | str) -> dict[str, int]:
    """``fo_mktlots.csv`` (space-padded): first non-empty month column after SYMBOL = current lot size."""
    text = decode(data)
    reader = csv.reader(io.StringIO(text))
    header = [h.strip().upper() for h in next(reader, [])]
    if "SYMBOL" not in header:
        raise ParseError("fo_mktlots: SYMBOL column not found")
    sym_idx = header.index("SYMBOL")
    out: dict[str, int] = {}
    for raw in reader:
        if len(raw) <= sym_idx:
            continue
        sym = raw[sym_idx].strip()
        if not sym or sym.upper() == "SYMBOL":
            continue
        for cell in raw[sym_idx + 1 :]:
            lot = integer(cell)
            if lot:
                out[sym] = lot
                break
    return out


# ------------------------------------------------------------------ RSS
_SUBJECT_RE = re.compile(r"\|\s*SUBJECT\s*:\s*(.+)$", re.DOTALL)
_DESC_SYMBOL_RE = re.compile(r"^([A-Z0-9][A-Z0-9&\-]{0,19})\s+:\s")


def parse_nse_rss(data: bytes | str, source: str = "NSE announcements RSS", feed_url: str | None = None) -> list[Announcement]:
    """NSE RSS: title = company, description = text ``|SUBJECT: <subject>``, pubDate ``05-Oct-2026 09:03:37`` IST."""
    items = parse_feed(data, source=source, source_tier="primary", feed_url=feed_url)
    for a in items:
        a.company = a.headline
        body = a.body or ""
        m = _SUBJECT_RE.search(body)
        subject = m.group(1).strip() if m else None
        sm = _DESC_SYMBOL_RE.match(body)
        if sm:
            a.symbol = sm.group(1)
        if subject:
            a.headline = f"{a.company}: {subject}"
            a.raw["subject"] = subject
        a.url = a.url or None
    return items


# ------------------------------------------------------------------ www JSON APIs
def parse_holidays(obj: dict[str, Any], segment: str | None = "CM") -> list[HolidayRecord]:
    """``/api/holiday-master?type=trading`` → holidays for ``segment`` (None = all segments)."""
    out: list[HolidayRecord] = []
    for seg, items in obj.items():
        if segment is not None and seg != segment:
            continue
        for it in items or []:
            d = parse_date(it.get("tradingDate"))
            if d is not None:
                out.append(HolidayRecord(date=d, description=(it.get("description") or "").strip(), segment=seg))
    return sorted(out, key=lambda h: (h.segment, h.date))


def parse_fii_dii(obj: list[dict[str, Any]]) -> list[FlowRecord]:
    """``/api/fiidiiTradeReact`` (₹ crore, provisional). Category ``FII/FPI`` → ``FII``."""
    out: list[FlowRecord] = []
    for it in obj:
        cat = (it.get("category") or "").upper()
        cat = "FII" if cat.startswith("FII") or "FPI" in cat else "DII" if cat.startswith("DII") else cat
        d = parse_date(it.get("date"))
        buy, sell, net = num(it.get("buyValue")), num(it.get("sellValue")), num(it.get("netValue"))
        if d is None or buy is None or sell is None:
            continue
        out.append(FlowRecord(d, cat, buy, sell, net if net is not None else round(buy - sell, 2)))
    return out


_AMT = r"R(?:s|e)\.?\s*([\d]+(?:\.\d+)?)\s*(?:/-)?"
_DIV_RE = re.compile(_AMT + r"\s*Per\s*Sh(?:are)?\b", re.IGNORECASE)
_SPLIT_RE = re.compile(r"From\s+" + _AMT + r".*?To\s+" + _AMT, re.IGNORECASE)
_RATIO_RE = re.compile(r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)")
_PREMIUM_RE = re.compile(r"Premium\s+" + _AMT, re.IGNORECASE)
_NON_EQUITY_RE = re.compile(r"\b(NCRPS|CRPS|PREFERENCE|DEBENTURE|NCD|WARRANT)", re.IGNORECASE)


def parse_ca_subject(subject: str) -> tuple[str, float | None, float | None, float | None]:
    """Classify an NSE corporate-action subject → (action_type, ratio_from, ratio_to, amount).

    * dividend: amount = sum of all per-share amounts (e.g. interim + special) in INR.
    * split / consolidation: ratio_from = old face value, ratio_to = new face value.
    * bonus ``a:b``: ratio_from = a (new shares), ratio_to = b (held). Bonus of non-equity instruments
      (e.g. "Bonus Ncrps 46:1") is classified ``other`` because it does not change the equity count.
    * rights ``a:b @ Premium Rs p``: ratio_from = a, ratio_to = b, amount = premium p.
    """
    s = " ".join(subject.split())
    low = s.lower()
    if "split" in low or "sub-division" in low or "subdivision" in low or "consolidation" in low:
        m = _SPLIT_RE.search(s)
        return "split", (float(m.group(1)) if m else None), (float(m.group(2)) if m else None), None
    if "bonus" in low:
        if _NON_EQUITY_RE.search(s):
            return "other", None, None, None
        m = _RATIO_RE.search(s)
        return "bonus", (float(m.group(1)) if m else None), (float(m.group(2)) if m else None), None
    if "rights" in low:
        m, p = _RATIO_RE.search(s), _PREMIUM_RE.search(s)
        return (
            "rights", (float(m.group(1)) if m else None), (float(m.group(2)) if m else None),
            (float(p.group(1)) if p else None),
        )
    if "buy back" in low or "buyback" in low:
        return "buyback", None, None, None
    if "demerger" in low:
        return "demerger", None, None, None
    if "dividend" in low:
        amounts = [float(x) for x in _DIV_RE.findall(s)]
        return "dividend", None, None, (round(sum(amounts), 6) if amounts else None)
    return "other", None, None, None


def parse_corporate_actions(obj: list[dict[str, Any]]) -> list[CorporateActionRecord]:
    """``/api/corporates-corporateActions`` → records with parsed type/ratios/amount."""
    out: list[CorporateActionRecord] = []
    for it in obj:
        subject = (it.get("subject") or "").strip()
        sym = clean(it.get("symbol"))
        if not sym or not subject:
            continue
        action, rf, rt, amt = parse_ca_subject(subject)
        out.append(
            CorporateActionRecord(
                symbol=sym, subject=subject, ex_date=parse_date(it.get("exDate")),
                record_date=parse_date(it.get("recDate")), action_type=action,
                ratio_from=rf, ratio_to=rt, amount=amt, raw=dict(it),
            )
        )
    return out


def parse_event_calendar(obj: list[dict[str, Any]]) -> list[EventRecord]:
    out: list[EventRecord] = []
    for it in obj:
        d, sym = parse_date(it.get("date")), clean(it.get("symbol"))
        if d is None or not sym:
            continue
        out.append(EventRecord(sym, d, (it.get("purpose") or "").strip(), clean(it.get("bm_desc"))))
    return out


def _is_consolidated(v: Any) -> bool:
    s = (v or "").strip().lower()
    return s.startswith("consolidated")


def _audited(v: Any) -> bool | None:
    s = (v or "").strip().lower().replace("-", "")
    if not s:
        return None
    return s.startswith("audited")


def parse_result_filings_legacy(obj: list[dict[str, Any]]) -> list[ResultFiling]:
    """``/api/corporates-financial-results`` (legacy list, data up to Dec-2024)."""
    out: list[ResultFiling] = []
    for it in obj:
        end = parse_date(it.get("toDate"))
        if end is None or not it.get("symbol"):
            continue
        out.append(
            ResultFiling(
                symbol=it["symbol"], period_end=end, period_start=parse_date(it.get("fromDate")),
                consolidated=_is_consolidated(it.get("consolidated")), audited=_audited(it.get("audited")),
                is_bank=(it.get("bank") or "").upper() == "Y", broadcast_at=parse_ist_datetime(it.get("broadCastDate")),
                xbrl_url=clean(it.get("xbrl")), period_type=(clean(it.get("period")) or "quarterly").lower(),
            )
        )
    return out


def parse_integrated_filings(obj: dict[str, Any] | list[dict[str, Any]]) -> list[ResultFiling]:
    """``/api/integrated-filing-results`` (newer filings). Period start/bank flag are not in the list."""
    items = obj.get("data", []) if isinstance(obj, dict) else obj
    out: list[ResultFiling] = []
    for it in items:
        end = parse_date(it.get("qe_Date"))
        if end is None or not it.get("symbol"):
            continue
        xbrl = clean(it.get("xbrl"))
        out.append(
            ResultFiling(
                symbol=it["symbol"], period_end=end, period_start=None,
                consolidated=_is_consolidated(it.get("consolidated")), audited=_audited(it.get("audited")),
                is_bank=False, broadcast_at=parse_ist_datetime(it.get("broadcast_Date")),
                xbrl_url=xbrl if xbrl and xbrl.lower().endswith(".xml") else None, period_type="quarterly",
            )
        )
    return out


def merge_result_filings(legacy: list[ResultFiling], integrated: list[ResultFiling]) -> list[ResultFiling]:
    """Union keyed by (period_end, consolidated); integrated filings win on overlap, latest broadcast within a
    source wins (revisions). The legacy bank flag is carried over. Sorted newest first."""
    def latest(rows: list[ResultFiling]) -> dict[tuple[date, bool], ResultFiling]:
        best: dict[tuple[date, bool], ResultFiling] = {}
        for f in rows:
            k = (f.period_end, f.consolidated)
            cur = best.get(k)
            if cur is None or (f.broadcast_at and (cur.broadcast_at is None or f.broadcast_at > cur.broadcast_at)):
                best[k] = f
        return best

    merged = latest(legacy)
    is_bank = any(f.is_bank for f in legacy)
    for k, f in latest(integrated).items():
        old = merged.get(k)
        if old is not None and f.period_start is None:
            f.period_start = old.period_start
        f.is_bank = f.is_bank or is_bank
        merged[k] = f
    return sorted(merged.values(), key=lambda f: (f.period_end, f.consolidated), reverse=True)


def parse_shareholding(obj: list[dict[str, Any]]) -> list[ShareholdingRecord]:
    """``/api/corporate-share-holdings-master`` → promoter/public % per quarter."""
    out: list[ShareholdingRecord] = []
    for it in obj:
        d, sym = parse_date(it.get("date")), clean(it.get("symbol"))
        if d is None or not sym:
            continue
        out.append(
            ShareholdingRecord(
                symbol=sym, period_end=d, promoter_pct=num(it.get("pr_and_prgrp")), public_pct=num(it.get("public_val")),
                broadcast_at=parse_ist_datetime(it.get("broadcastDate")), xbrl_url=clean(it.get("xbrl")),
            )
        )
    return out


# ------------------------------------------------------------------ XBRL results
_XBRL_FIELDS: dict[str, tuple[str, ...]] = {
    "revenue": ("RevenueFromOperations", "InterestEarned", "TotalRevenueFromOperations"),
    "other_income": ("OtherIncome",),
    "total_income": ("Income", "TotalIncome"),
    "total_expenses": ("Expenses", "TotalExpenses", "ExpenditureExcludingProvisionsAndContingencies"),
    "finance_costs": ("FinanceCosts",),  # bank "InterestExpended" is cost of funds, kept in raw only
    "depreciation": ("DepreciationDepletionAndAmortisationExpense", "DepreciationAndAmortisationExpense"),
    "pbt": ("ProfitBeforeTax", "ProfitLossFromOrdinaryActivitiesBeforeTax"),
    "tax": ("TaxExpense",),
    "pat": ("ProfitLossForPeriod", "ProfitLossForThePeriod", "NetProfitLossForThePeriod"),
    "pat_owners": ("ProfitOrLossAttributableToOwnersOfParent",),
    "eps_basic": (
        "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
        "BasicEarningsLossPerShareFromContinuingOperations",
        "BasicEarningsPerShareAfterExtraordinaryItems",
    ),
    "eps_diluted": (
        "DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
        "DilutedEarningsLossPerShareFromContinuingOperations",
        "DilutedEarningsPerShareAfterExtraordinaryItems",
    ),
    "paid_up_capital": ("PaidUpValueOfEquityShareCapital",),
    "face_value": ("FaceValueOfEquityShareCapital",),
    "debt_equity": ("DebtEquityRatio",),
    "interest_coverage": ("InterestServiceCoverageRatio",),
}
_BANK_TAGS = {"InterestEarned", "InterestExpended"}


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _select_context(contexts: dict[str, dict[str, Any]], facts: dict[str, dict[str, str]]) -> str:
    """Pick the context for the current reporting period.

    Candidates are dimensionless duration contexts whose period equals the DateOfStart/EndOfReportingPeriod
    reported in *that* context (filings sometimes declare a YTD context with the quarter's dates, so the
    context's own facts are the tie-breaker). The period is anchored on ``OneD`` when it reports dates.
    """
    def own_dates(cid: str) -> tuple[date | None, date | None]:
        f = facts.get(cid, {})
        return parse_date(f.get("DateOfStartOfReportingPeriod")), parse_date(f.get("DateOfEndOfReportingPeriod"))

    anchor = own_dates("OneD") if "OneD" in contexts else (None, None)
    candidates: list[str] = []
    for cid, c in contexts.items():
        if c["dimensional"] or c["start"] is None:
            continue
        s, e = own_dates(cid)
        if s is None or e is None or (c["start"], c["end"]) != (s, e):
            continue
        if anchor != (None, None) and (s, e) != anchor:
            continue
        candidates.append(cid)
    if "OneD" in candidates:
        return "OneD"
    if candidates:
        return min(candidates, key=lambda cid: (contexts[cid]["end"] - contexts[cid]["start"]).days)
    if "OneD" in contexts:
        return "OneD"
    raise ParseError("XBRL: could not determine the reporting-period context")


def parse_xbrl_financials(
    data: bytes | str, symbol: str | None = None, *, consolidated: bool | None = None, is_bank: bool | None = None
) -> FinancialStatement:
    """Parse an NSE/BSE result XBRL instance (namespace-agnostic). Values are absolute INR; missing → None."""
    try:
        root = ET.fromstring(data.encode() if isinstance(data, str) else data)
    except ET.ParseError as exc:
        raise ParseError(f"invalid XBRL: {exc}") from exc

    contexts: dict[str, dict[str, Any]] = {}
    facts: dict[str, dict[str, str]] = {}
    for el in root:
        name = _ln(el.tag)
        if name == "context":
            start = end = None
            dimensional = False
            for sub in el.iter():
                sn = _ln(sub.tag)
                if sn == "startDate":
                    start = parse_date(sub.text)
                elif sn in ("endDate", "instant"):
                    end = parse_date(sub.text)
                elif sn in ("scenario", "segment"):
                    dimensional = True
            contexts[el.get("id", "")] = {"start": start, "end": end, "dimensional": dimensional}
        elif el.get("contextRef"):
            facts.setdefault(el.get("contextRef", ""), {}).setdefault(name, (el.text or "").strip())

    if not facts:
        raise ParseError("XBRL: no facts found")
    ctx = _select_context(contexts, facts)
    f = facts.get(ctx, {})

    def pick(names: tuple[str, ...]) -> float | None:
        for n in names:
            v = num(f.get(n))
            if v is not None:
                return v
        return None

    period_start = parse_date(f.get("DateOfStartOfReportingPeriod")) or contexts.get(ctx, {}).get("start")
    period_end = parse_date(f.get("DateOfEndOfReportingPeriod")) or contexts.get(ctx, {}).get("end")
    if period_end is None:
        raise ParseError("XBRL: reporting period end not found")
    nature = f.get("NatureOfReportStandaloneConsolidated")
    cons = _is_consolidated(nature) if nature else bool(consolidated)
    bank = bool(is_bank) or any(t in f for t in _BANK_TAGS)
    raw: dict[str, Any] = {"context": ctx}
    for k, v in f.items():
        fv = num(v)
        if fv is not None:
            raw[k] = fv
        elif len(v) <= 200:  # skip long text blocks (notes)
            raw[k] = v
    return FinancialStatement(
        symbol=symbol or f.get("Symbol") or "",
        period_start=period_start,
        period_end=period_end,
        consolidated=cons,
        is_bank=bank,
        raw=raw,
        **{field: pick(tags) for field, tags in _XBRL_FIELDS.items()},
    )
