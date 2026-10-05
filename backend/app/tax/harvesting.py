"""Tax-loss harvesting *view* (informational, pure). Never a sell recommendation.

For each position with an unrealized capital loss, the hypothetical sale is the WHOLE position at LTP on
``as_of`` (selling part of a position consumes the oldest lots first under FIFO, so specific loss lots cannot be
picked). The tax impact is ``tax(realized + hypothetical) - tax(realized)`` for the current tax year, so
set-off ordering, the LTCG exemption already used and brought-forward losses are all respected.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.portfolio.lots import Lot
from app.tax.common import (
    DISCLAIMER,
    ESTIMATED,
    INCOMPLETE_MESSAGE,
    ZERO,
    dedupe,
    inr,
    jsonable,
    tax_year_of,
)
from app.tax.engine import (
    GainLine,
    OpenLotPrice,
    TaxProfileIn,
    compute_tax_year,
    hypothetical_sale_lines,
)
from app.tax.rules import RuleBook

HARVEST_LABEL = "Tax planning estimate — verify with a qualified tax professional."
NOT_A_RECOMMENDATION = "Not a sell recommendation."


@dataclass
class HarvestLot:
    lot_id: str
    quantity: Decimal
    acquired_date: date
    holding_days: int
    term: str  # if sold on as_of
    capital_gain: Decimal


@dataclass
class HarvestCandidate:
    symbol: str
    quantity: Decimal
    cost_of_acquisition: Decimal
    market_value: Decimal
    unrealized_gain: Decimal  # negative for a loss (tax view: STT not deductible)
    unrealized_loss: Decimal  # magnitude of the net loss
    short_term_loss: Decimal  # net STCL the sale would create
    long_term_loss: Decimal  # net LTCL the sale would create
    classification: str  # STCG | LTCG | MIXED (term of the lots if sold on as_of)
    min_holding_days: int
    max_holding_days: int
    lots: list[HarvestLot]
    potential_offset: list[str]
    realized_net_stcg_this_year: Decimal
    realized_net_ltcg_this_year: Decimal
    estimated_tax_without_sale: Decimal
    estimated_tax_with_sale: Decimal
    estimated_tax_impact: Decimal  # with - without (negative = lower estimated tax)
    carry_forward_stcl_after: Decimal
    carry_forward_ltcl_after: Decimal
    status: str
    incomplete_reasons: list[str]
    notes: list[str] = field(default_factory=list)
    label: str = HARVEST_LABEL
    note: str = NOT_A_RECOMMENDATION
    is_estimate: bool = True


@dataclass
class HarvestReport:
    as_of: date
    tax_year: str
    candidates: list[HarvestCandidate]
    status: str
    incomplete_reasons: list[str]
    message: str | None
    rule_set_version: str
    notes: list[str] = field(default_factory=list)
    label: str = HARVEST_LABEL
    note: str = NOT_A_RECOMMENDATION
    estimate_label: str = ESTIMATED
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


def _offset_text(stcl: Decimal, ltcl: Decimal) -> list[str]:
    out: list[str] = []
    if stcl > 0:
        out.append(
            f"Short-term capital loss of {inr(stcl)} can be set off against STCG first and then LTCG "
            "of this tax year; any balance can be carried forward for 8 years."
        )
    if ltcl > 0:
        out.append(
            f"Long-term capital loss of {inr(ltcl)} can be set off only against LTCG (not STCG); "
            "any balance can be carried forward for 8 years."
        )
    out.append("Carry-forward requires the income-tax return to be filed by the due date.")
    return out


def harvest_candidates(
    open_lots_with_ltp: Iterable[OpenLotPrice | tuple[Lot, Decimal]],
    realized_lines_this_year: Iterable[GainLine],
    profile: TaxProfileIn,
    rulebook: RuleBook,
    as_of: date,
    *,
    charges_engine: Any | None = None,
) -> HarvestReport:
    tax_year = tax_year_of(as_of)
    realized = [ln for ln in realized_lines_this_year if ln.tax_year == tax_year]
    baseline = compute_tax_year(realized, tax_year, profile, rulebook)
    items = [i if isinstance(i, OpenLotPrice) else OpenLotPrice(i[0], i[1]) for i in open_lots_with_ltp]
    by_symbol: dict[str, list[OpenLotPrice]] = {}
    for it in items:
        if it.lot.remaining_quantity > 0:
            by_symbol.setdefault(it.lot.symbol, []).append(it)

    realized_st = baseline.totals["STCG"].net
    realized_lt = baseline.totals["LTCG"].net
    candidates: list[HarvestCandidate] = []
    report_notes: list[str] = []
    for symbol, group in sorted(by_symbol.items()):
        hyp, notes = hypothetical_sale_lines(group, as_of, rulebook, charges_engine)
        report_notes.extend(notes)
        net = sum((ln.capital_gain for ln in hyp), ZERO)
        if net >= 0:
            continue
        stcl = -sum((ln.capital_gain for ln in hyp if ln.term == "STCG"), ZERO)
        ltcl = -sum((ln.capital_gain for ln in hyp if ln.term == "LTCG"), ZERO)
        with_sale = compute_tax_year(realized + hyp, tax_year, profile, rulebook)
        terms = {ln.term for ln in hyp}
        reasons = dedupe(with_sale.incomplete_reasons)
        cand_notes = [
            "Under FIFO, a partial sale consumes the oldest lots first; the whole position is assumed sold.",
            "Repurchasing resets cost and holding period; consider anti-avoidance provisions with your adviser.",
        ]
        if stcl < 0 or ltcl < 0:
            cand_notes.append("Some lots are at a gain; figures above are net per term.")
        candidates.append(HarvestCandidate(
            symbol=symbol,
            quantity=sum((ln.quantity for ln in hyp), ZERO),
            cost_of_acquisition=sum((ln.cost_of_acquisition for ln in hyp), ZERO),
            market_value=sum((ln.sale_value for ln in hyp), ZERO),
            unrealized_gain=net,
            unrealized_loss=-net,
            short_term_loss=max(stcl, ZERO),
            long_term_loss=max(ltcl, ZERO),
            classification=terms.pop() if len(terms) == 1 else "MIXED",
            min_holding_days=min(ln.holding_days for ln in hyp),
            max_holding_days=max(ln.holding_days for ln in hyp),
            lots=[
                HarvestLot(ln.lot_id, ln.quantity, ln.acquired_date, ln.holding_days, ln.term, ln.capital_gain)
                for ln in hyp
            ],
            potential_offset=_offset_text(max(stcl, ZERO), max(ltcl, ZERO)),
            realized_net_stcg_this_year=realized_st,
            realized_net_ltcg_this_year=realized_lt,
            estimated_tax_without_sale=baseline.total_tax_estimate,
            estimated_tax_with_sale=with_sale.total_tax_estimate,
            estimated_tax_impact=with_sale.total_tax_estimate - baseline.total_tax_estimate,
            carry_forward_stcl_after=with_sale.carry_forward.stcl,
            carry_forward_ltcl_after=with_sale.carry_forward.ltcl,
            status="incomplete" if reasons else "complete",
            incomplete_reasons=reasons,
            notes=cand_notes,
        ))
    candidates.sort(key=lambda c: (-c.unrealized_loss, c.symbol))
    reasons = dedupe(baseline.incomplete_reasons + [r for c in candidates for r in c.incomplete_reasons])
    return HarvestReport(
        as_of=as_of,
        tax_year=tax_year,
        candidates=candidates,
        status="incomplete" if reasons else "complete",
        incomplete_reasons=reasons,
        message=INCOMPLETE_MESSAGE if reasons else None,
        rule_set_version=rulebook.version,
        notes=dedupe(report_notes),
    )
