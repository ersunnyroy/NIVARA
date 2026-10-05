"""FIFO tax lots for Indian listed equity (pure; no DB).

Indian demat practice: shares are deemed sold first-in-first-out (CBDT Circular No. 768 dated 24-Jun-1998).

Conventions
-----------
* ``TxnIn.charges`` is the *all-in* charges of the order (brokerage, STT, exchange, SEBI, stamp, GST, DP);
  ``TxnIn.stt`` is the STT portion already included in ``charges``. STT is tracked separately because it is not
  deductible when computing capital gains (but is a cost for trading P&L).
* Buy charges stay with a lot and are allocated pro-rata by quantity as the lot is consumed; sell charges are
  allocated pro-rata by quantity across the lots a sell consumes. The last slice takes the residual so the
  allocations always sum exactly to the original amounts.
* Processing is chronological per symbol. Within a day: corporate actions (ex-date) first, then buys, then
  intraday sells (matched only against that day's intraday buys - allowing short-then-cover), then delivery
  sells (FIFO over delivery lots). Intraday buys not squared off the same day are carried as delivery lots.
* Split (face value ``a`` -> ``b``): quantity x a/b, cost per share / (a/b), acquisition date unchanged.
* Bonus ``a:b`` (``a`` new shares for every ``b`` held): one NEW zero-cost lot of floor(holding x a/b) shares
  acquired on the ex-date. Indian tax treats bonus shares as nil cost with holding from allotment; the ex-date is
  used as a proxy for the allotment date. Fractional entitlements are ignored (usually settled in cash).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from app.tax.common import ZERO, D

DELIVERY = "delivery"
INTRADAY = "intraday"
_SEGMENT_MAP = {
    "delivery": DELIVERY, "equity_delivery": DELIVERY, "cnc": DELIVERY,
    "intraday": INTRADAY, "equity_intraday": INTRADAY, "mis": INTRADAY,
}


def _segment(value: str) -> str:
    key = (value or DELIVERY).strip().lower()
    if key not in _SEGMENT_MAP:
        raise ValueError(f"FIFO lots support equity delivery/intraday only, got segment {value!r}")
    return _SEGMENT_MAP[key]


@dataclass(frozen=True)
class TxnIn:
    id: Any
    symbol: str
    side: str  # BUY | SELL
    quantity: Decimal
    price: Decimal
    trade_date: date
    charges: Decimal = ZERO  # all-in, incl. STT
    stt: Decimal = ZERO  # STT portion of `charges`
    segment: str = DELIVERY  # delivery | intraday
    fmv_31jan2018: Decimal | None = None  # per share, grandfathering input (buys on/before 31-Jan-2018)


@dataclass(frozen=True)
class CorpActionIn:
    symbol: str
    ex_date: date
    kind: str  # "split" | "bonus"
    ratio_from: Decimal  # split: old face value; bonus: new shares (a)
    ratio_to: Decimal  # split: new face value; bonus: shares held (b)


@dataclass
class Lot:
    lot_id: str
    symbol: str
    segment: str
    acquired_date: date
    quantity: Decimal  # lot size (adjusted for splits)
    remaining_quantity: Decimal
    cost_per_share: Decimal
    buy_charges: Decimal  # charges (incl. STT) attributable to the REMAINING quantity
    buy_stt: Decimal  # STT portion of buy_charges
    buy_txn_id: Any | None = None
    is_bonus: bool = False
    fmv_31jan2018: Decimal | None = None  # per share, adjusted for subsequent splits
    adjustments: list[str] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.remaining_quantity > 0

    @property
    def remaining_cost(self) -> Decimal:
        return self.remaining_quantity * self.cost_per_share


@dataclass(frozen=True)
class Match:
    """One slice of a lot consumed by a sell (maps to models.portfolio.RealizedGain)."""

    lot_id: str
    buy_txn_id: Any | None
    sell_txn_id: Any
    symbol: str
    segment: str
    quantity: Decimal
    acquired_date: date
    sold_date: date
    cost_per_share: Decimal
    sell_price: Decimal
    purchase_value: Decimal
    sale_value: Decimal
    buy_charges_alloc: Decimal  # incl. buy STT
    sell_charges_alloc: Decimal  # incl. sell STT
    buy_stt_alloc: Decimal
    sell_stt_alloc: Decimal
    holding_days: int
    is_bonus: bool = False
    fmv_31jan2018: Decimal | None = None  # per share

    @property
    def stt_alloc(self) -> Decimal:
        return self.buy_stt_alloc + self.sell_stt_alloc

    @property
    def charges_alloc(self) -> Decimal:
        return self.buy_charges_alloc + self.sell_charges_alloc

    @property
    def gross_pnl(self) -> Decimal:
        return self.sale_value - self.purchase_value

    @property
    def trading_pnl(self) -> Decimal:
        """P&L after ALL charges (incl. STT/DP), before income tax."""
        return self.gross_pnl - self.charges_alloc


@dataclass
class LotLedger:
    lots: list[Lot]  # every lot ever created (open and closed)
    matches: list[Match]
    notes: list[str] = field(default_factory=list)

    @property
    def open_lots(self) -> list[Lot]:
        return [lot for lot in self.lots if lot.is_open]

    def open_lots_for(self, symbol: str) -> list[Lot]:
        return [lot for lot in self.open_lots if lot.symbol == symbol]

    def quantity_held(self, symbol: str) -> Decimal:
        return sum((lot.remaining_quantity for lot in self.open_lots_for(symbol)), ZERO)


@dataclass(frozen=True)
class AverageCost:
    quantity: Decimal
    total_cost: Decimal
    average_price: Decimal | None
    total_cost_incl_charges: Decimal
    average_price_incl_charges: Decimal | None


def average_cost(open_lots: Iterable[Lot]) -> AverageCost:
    """Weighted average cost of the remaining quantity (display only; tax uses FIFO lots).

    Bonus lots carry zero cost and therefore lower the average, as they do for tax purposes.
    """
    lots = [lot for lot in open_lots if lot.remaining_quantity > 0]
    symbols = {lot.symbol for lot in lots}
    if len(symbols) > 1:
        raise ValueError(f"average_cost expects lots of a single symbol, got {sorted(symbols)}")
    qty = sum((lot.remaining_quantity for lot in lots), ZERO)
    cost = sum((lot.remaining_cost for lot in lots), ZERO)
    cost_incl = cost + sum((lot.buy_charges for lot in lots), ZERO)
    if qty == 0:
        return AverageCost(ZERO, ZERO, None, ZERO, None)
    return AverageCost(qty, cost, cost / qty, cost_incl, cost_incl / qty)


def _validate(t: TxnIn) -> tuple[str, str]:
    side = (t.side or "").strip().upper()
    if side not in ("BUY", "SELL"):
        raise ValueError(f"Transaction {t.id}: side must be BUY or SELL, got {t.side!r}")
    if D(t.quantity) <= 0:
        raise ValueError(f"Transaction {t.id}: quantity must be positive")
    if D(t.price) < 0:
        raise ValueError(f"Transaction {t.id}: price must be non-negative")
    if D(t.charges) < 0 or D(t.stt) < 0:
        raise ValueError(f"Transaction {t.id}: charges/STT must be non-negative")
    return side, _segment(t.segment)


class _SymbolBook:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.delivery: list[Lot] = []  # FIFO queue
        self.all_lots: list[Lot] = []
        self.matches: list[Match] = []
        self.notes: list[str] = []

    # -- lots ---------------------------------------------------------------------------------------------
    def new_lot(self, t: TxnIn, segment: str) -> Lot:
        lot = Lot(
            lot_id=str(t.id),
            symbol=self.symbol,
            segment=segment,
            acquired_date=t.trade_date,
            quantity=D(t.quantity),
            remaining_quantity=D(t.quantity),
            cost_per_share=D(t.price),
            buy_charges=D(t.charges),
            buy_stt=D(t.stt),
            buy_txn_id=t.id,
            fmv_31jan2018=None if t.fmv_31jan2018 is None else D(t.fmv_31jan2018),
        )
        self.all_lots.append(lot)
        return lot

    def apply_corp_action(self, ca: CorpActionIn) -> None:
        kind = ca.kind.strip().lower()
        a, b = D(ca.ratio_from), D(ca.ratio_to)
        if a <= 0 or b <= 0:
            raise ValueError(f"Corporate action {kind} on {self.symbol} {ca.ex_date}: ratios must be positive")
        open_lots = [lot for lot in self.delivery if lot.remaining_quantity > 0]
        if kind == "split":
            factor = a / b
            for lot in open_lots:
                lot.quantity *= factor
                lot.remaining_quantity *= factor
                lot.cost_per_share /= factor
                if lot.fmv_31jan2018 is not None:
                    lot.fmv_31jan2018 /= factor
                lot.adjustments.append(
                    f"Split on {ca.ex_date.isoformat()} (FV {a}->{b}): quantity x{factor.normalize()}, "
                    "cost per share adjusted; acquisition date unchanged."
                )
                if lot.remaining_quantity != lot.remaining_quantity.to_integral_value():
                    lot.adjustments.append("Fractional quantity after split (usually settled in cash).")
        elif kind == "bonus":
            held = sum((lot.remaining_quantity for lot in open_lots), ZERO)
            new_qty = (held * a / b).to_integral_value(rounding=ROUND_FLOOR)
            if new_qty > 0:
                lot = Lot(
                    lot_id=f"BONUS:{self.symbol}:{ca.ex_date.isoformat()}",
                    symbol=self.symbol,
                    segment=DELIVERY,
                    acquired_date=ca.ex_date,
                    quantity=new_qty,
                    remaining_quantity=new_qty,
                    cost_per_share=ZERO,
                    buy_charges=ZERO,
                    buy_stt=ZERO,
                    buy_txn_id=None,
                    is_bonus=True,
                    adjustments=[
                        (
                            f"Bonus {a.normalize()}:{b.normalize()} on {ca.ex_date.isoformat()} for "
                            f"{held.normalize()} shares held: nil cost; holding period from allotment "
                            "(ex-date used as proxy)."
                        )
                    ],
                )
                self.delivery.append(lot)
                self.all_lots.append(lot)
        else:
            raise ValueError(f"Unsupported corporate action kind {ca.kind!r} (expected split|bonus)")

    # -- matching -----------------------------------------------------------------------------------------
    def match_sell(self, t: TxnIn, pool: list[Lot], segment: str) -> None:
        qty = D(t.quantity)
        available = sum((lot.remaining_quantity for lot in pool), ZERO)
        if qty > available:
            where = "same-day intraday buys" if segment == INTRADAY else "open lots"
            raise ValueError(
                f"Oversell: transaction {t.id} sells {qty.normalize()} {self.symbol} on {t.trade_date.isoformat()} "
                f"but only {available.normalize()} available in {where}."
            )
        sell_charges, sell_stt = D(t.charges), D(t.stt)
        price = D(t.price)
        left = qty
        charges_left, stt_left = sell_charges, sell_stt
        for lot in pool:
            if left == 0:
                break
            if lot.remaining_quantity <= 0:
                continue
            take = min(lot.remaining_quantity, left)
            # buy-side allocation (residual on full consumption)
            if take == lot.remaining_quantity:
                buy_alloc, buy_stt_alloc = lot.buy_charges, lot.buy_stt
            else:
                buy_alloc = lot.buy_charges * take / lot.remaining_quantity
                buy_stt_alloc = lot.buy_stt * take / lot.remaining_quantity
            # sell-side allocation (residual on the last slice)
            if take == left:
                sell_alloc, sell_stt_alloc = charges_left, stt_left
            else:
                sell_alloc = sell_charges * take / qty
                sell_stt_alloc = sell_stt * take / qty
            self.matches.append(Match(
                lot_id=lot.lot_id,
                buy_txn_id=lot.buy_txn_id,
                sell_txn_id=t.id,
                symbol=self.symbol,
                segment=segment,
                quantity=take,
                acquired_date=lot.acquired_date,
                sold_date=t.trade_date,
                cost_per_share=lot.cost_per_share,
                sell_price=price,
                purchase_value=take * lot.cost_per_share,
                sale_value=take * price,
                buy_charges_alloc=buy_alloc,
                sell_charges_alloc=sell_alloc,
                buy_stt_alloc=buy_stt_alloc,
                sell_stt_alloc=sell_stt_alloc,
                holding_days=(t.trade_date - lot.acquired_date).days,
                is_bonus=lot.is_bonus,
                fmv_31jan2018=lot.fmv_31jan2018,
            ))
            lot.remaining_quantity -= take
            lot.buy_charges -= buy_alloc
            lot.buy_stt -= buy_stt_alloc
            charges_left -= sell_alloc
            stt_left -= sell_stt_alloc
            left -= take


def build_lots(txns: Iterable[TxnIn], corp_actions: Iterable[CorpActionIn] = ()) -> LotLedger:
    """Build FIFO lots and sell matches from transactions and corporate actions (see module docstring)."""
    by_symbol: dict[str, list[tuple[int, TxnIn, str, str]]] = defaultdict(list)
    for idx, t in enumerate(txns):
        side, seg = _validate(t)
        by_symbol[t.symbol].append((idx, t, side, seg))
    cas_by_symbol: dict[str, list[CorpActionIn]] = defaultdict(list)
    for ca in corp_actions:
        cas_by_symbol[ca.symbol].append(ca)

    all_lots: list[Lot] = []
    matches: list[Match] = []
    notes: list[str] = []
    for symbol in sorted(set(by_symbol) | set(cas_by_symbol)):
        book = _SymbolBook(symbol)
        days: dict[date, list[tuple[int, TxnIn, str, str]]] = defaultdict(list)
        for item in by_symbol.get(symbol, []):
            days[item[1].trade_date].append(item)
        cas_by_day: dict[date, list[CorpActionIn]] = defaultdict(list)
        for ca in cas_by_symbol.get(symbol, []):
            cas_by_day[ca.ex_date].append(ca)

        for day in sorted(set(days) | set(cas_by_day)):
            for ca in cas_by_day.get(day, []):
                book.apply_corp_action(ca)
            items = sorted(days.get(day, []), key=lambda x: x[0])
            intraday_pool: list[Lot] = []
            for _, t, side, seg in items:
                if side == "BUY":
                    lot = book.new_lot(t, seg)
                    (intraday_pool if seg == INTRADAY else book.delivery).append(lot)
            for _, t, side, seg in items:
                if side == "SELL" and seg == INTRADAY:
                    book.match_sell(t, intraday_pool, INTRADAY)
            for _, t, side, seg in items:
                if side == "SELL" and seg == DELIVERY:
                    book.match_sell(t, book.delivery, DELIVERY)
            for lot in intraday_pool:
                if lot.remaining_quantity > 0:
                    lot.segment = DELIVERY
                    lot.adjustments.append(
                        f"Intraday buy on {day.isoformat()} not squared off the same day; carried as a delivery lot."
                    )
                    book.delivery.append(lot)
            book.delivery = [lot for lot in book.delivery if lot.remaining_quantity > 0]
        all_lots.extend(book.all_lots)
        matches.extend(book.matches)
        notes.extend(book.notes)
    return LotLedger(lots=all_lots, matches=matches, notes=notes)
