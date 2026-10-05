"""Tax rules engine: classification, per-match capital gains, tax-year computation (pure, ESTIMATED).

Modelling choices (all taxpayer-favourable where the law leaves an ordering choice; documented in set_off_log):

* Capital gain = (sale value - transfer expenses excl. STT) - (cost + acquisition expenses excl. STT).
  STT is not deductible for capital gains. Trading P&L deducts ALL charges incl. STT/DP.
* Intraday (``SPEC``) income is speculative business income: all charges incl. STT are deducted
  (s.36(1)(xv)), taxed at the user's slab rate.
* Gains are bucketed by (term, rate) because one tax year may contain transfers taxed at different rates
  (e.g. FY 2024-25 before/after 23-Jul-2024). Losses are pooled per term.
* Order of set-off: current-year STCL vs STCG -> current-year LTCL vs LTCG -> remaining current-year STCL vs LTCG
  -> b/f STCL vs STCG -> b/f LTCL vs LTCG -> remaining b/f STCL vs LTCG -> LTCG exemption (once per tax year)
  -> basic-exemption shortfall (residents). Within a term, losses/exemption are applied to the highest-rate
  bucket first. LTCL is applied to LTCG before leftover STCL so the more flexible STCL is preserved for
  carry-forward.
* Surcharge slab is chosen on total income = other income + net STCG + net LTCG (before the s.112A exemption)
  + net speculative income. For 111A/112A gains the surcharge is capped at the rule's cap (15%); for slab-rate
  income at the regime cap (new regime 25%). Marginal relief is not computed. If other income is unknown the
  surcharge is computed with other income = 0 (a lower bound) and the estimate is flagged incomplete.
* Rebate u/s 87A and rounding u/s 288A/288B are not modelled.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Any

from app.portfolio.lots import Lot, Match
from app.tax.common import (
    DISCLAIMER,
    ESTIMATED,
    INCOMPLETE_MESSAGE,
    ZERO,
    D,
    add_months,
    dedupe,
    inr,
    jsonable,
    money,
    pct,
    tax_year_bounds,
    tax_year_of,
)
from app.tax.rules import RuleBook, RuleNotFoundError, TaxRuleSpec

LISTED_EQUITY = "listed_equity_stt_paid"
INTRADAY_EQUITY = "intraday_equity"
UNREALIZED_LABEL = "Unrealized gains are informational and not necessarily currently taxable."
TERMS = ("STCG", "LTCG", "SPEC")


def asset_type_for_segment(segment: str) -> str:
    seg = (segment or "delivery").strip().lower()
    if seg in ("intraday", "equity_intraday", "mis"):
        return INTRADAY_EQUITY
    if seg in ("delivery", "equity_delivery", "cnc"):
        return LISTED_EQUITY
    raise ValueError(f"No tax asset type for segment {segment!r}")


def classify(acquired: date, sold: date, asset_type: str, rulebook: RuleBook) -> str:
    """STCG | LTCG | SPEC. LTCG only when held MORE than the rule's holding period (12 calendar months):
    sold > acquired + 12 months. Exactly 12 months is STCG."""
    if asset_type == INTRADAY_EQUITY:
        return "SPEC"
    if sold < acquired:
        raise ValueError(f"Sold date {sold} precedes acquisition date {acquired}")
    months = rulebook.holding_period_months(asset_type, sold)
    return "LTCG" if sold > add_months(acquired, months) else "STCG"


# --------------------------------------------------------------------------------------------------------------
# Per-match gain lines
# --------------------------------------------------------------------------------------------------------------

@dataclass
class GainLine:
    line_id: str
    symbol: str
    sell_txn_id: Any
    lot_id: str
    quantity: Decimal
    acquired_date: date
    sold_date: date
    holding_days: int
    asset_type: str
    term: str  # STCG | LTCG | SPEC | UNCLASSIFIED
    tax_year: str
    sale_value: Decimal
    purchase_value: Decimal
    cost_of_acquisition: Decimal  # incl. acquisition expenses (excl. STT); grandfathered where applicable
    acquisition_expenses: Decimal  # buy charges excl. STT
    transfer_expenses: Decimal  # sell charges excl. STT
    stt: Decimal  # buy + sell STT (not deductible for capital gains)
    capital_gain: Decimal  # taxable gain/loss; for SPEC = speculative income after ALL charges
    trading_pnl: Decimal  # after ALL charges incl. STT/DP
    rate: Decimal | None
    legal_reference: str | None = None
    grandfathered: bool = False
    is_hypothetical: bool = False
    flags: list[str] = field(default_factory=list)
    incomplete_reasons: list[str] = field(default_factory=list)
    rule: TaxRuleSpec | None = field(default=None, repr=False, compare=False)
    label: str = ESTIMATED


def capital_gain_for_match(
    match: Match,
    rulebook: RuleBook,
    fmv_31jan2018: Decimal | None = None,
    *,
    asset_type: str | None = None,
    is_hypothetical: bool = False,
) -> GainLine:
    """Tax view of one FIFO match. ``fmv_31jan2018`` is per share (defaults to the lot's value)."""
    asset = asset_type or asset_type_for_segment(match.segment)
    reasons: list[str] = []
    flags: list[str] = []
    buy_exp = match.buy_charges_alloc - match.buy_stt_alloc
    sell_exp = match.sell_charges_alloc - match.sell_stt_alloc
    trading_pnl = match.sale_value - match.purchase_value - match.buy_charges_alloc - match.sell_charges_alloc
    actual_cost = match.purchase_value + buy_exp
    cost = actual_cost
    grandfathered = False
    rule: TaxRuleSpec | None = None
    try:
        term = classify(match.acquired_date, match.sold_date, asset, rulebook)
        rule = rulebook.find_rule(asset, term, match.sold_date)
    except RuleNotFoundError:
        term = "UNCLASSIFIED"
    if rule is None:
        reasons.append(
            f"No tax rule in rule set {rulebook.version} for {asset} {term} transfers on "
            f"{match.sold_date.isoformat()} ({match.symbol})."
        )

    if term == "SPEC":
        gain = trading_pnl
        flags.append("Speculative income: all charges incl. STT deducted (s.36(1)(xv)).")
    else:
        if (
            term == "LTCG" and rule is not None and rule.grandfather_date is not None
            and match.acquired_date <= rule.grandfather_date
        ):
            fmv = fmv_31jan2018 if fmv_31jan2018 is not None else match.fmv_31jan2018
            if fmv is None:
                reasons.append(
                    f"FMV on {rule.grandfather_date.isoformat()} missing for {match.symbol} lot acquired "
                    f"{match.acquired_date.isoformat()}; grandfathering not applied (gain may be overstated)."
                )
            else:
                fmv_total = D(fmv) * match.quantity
                gf_cost = max(actual_cost, min(fmv_total, match.sale_value))
                if gf_cost != actual_cost:
                    grandfathered = True
                    flags.append(
                        f"Grandfathered cost {inr(gf_cost)} = max(actual cost {inr(actual_cost)}, "
                        f"min(FMV {inr(fmv_total)}, sale value {inr(match.sale_value)}))."
                    )
                cost = gf_cost
        gain = match.sale_value - sell_exp - cost
        if asset == LISTED_EQUITY and match.stt_alloc == 0 and not match.is_bonus:
            flags.append("No STT recorded; concessional rates assume STT was paid on the transfer.")
    if match.is_bonus:
        flags.append("Bonus shares: nil cost of acquisition; holding period from allotment.")

    return GainLine(
        line_id=f"{match.sell_txn_id}:{match.lot_id}",
        symbol=match.symbol,
        sell_txn_id=match.sell_txn_id,
        lot_id=match.lot_id,
        quantity=match.quantity,
        acquired_date=match.acquired_date,
        sold_date=match.sold_date,
        holding_days=match.holding_days,
        asset_type=asset,
        term=term,
        tax_year=tax_year_of(match.sold_date),
        sale_value=match.sale_value,
        purchase_value=match.purchase_value,
        cost_of_acquisition=cost,
        acquisition_expenses=buy_exp,
        transfer_expenses=sell_exp,
        stt=match.stt_alloc,
        capital_gain=gain,
        trading_pnl=trading_pnl,
        rate=rule.rate if rule is not None else None,
        legal_reference=rule.legal_reference if rule is not None else None,
        grandfathered=grandfathered,
        is_hypothetical=is_hypothetical,
        flags=flags,
        incomplete_reasons=reasons,
        rule=rule,
    )


def gain_lines_for_matches(matches: Iterable[Match], rulebook: RuleBook) -> list[GainLine]:
    return [capital_gain_for_match(m, rulebook) for m in matches]


# --------------------------------------------------------------------------------------------------------------
# Tax-year computation
# --------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class TaxProfileIn:
    residency: str | None = None  # resident | nri
    regime: str | None = None  # new | old
    other_taxable_income: Decimal | None = None  # excludes these gains
    slab_rate_for_business_income: Decimal | None = None  # fraction, e.g. 0.30
    carried_forward_stcl: Decimal | None = None
    carried_forward_ltcl: Decimal | None = None
    carried_forward_speculative: Decimal | None = None


@dataclass
class TermTotals:
    gross_gains: Decimal = ZERO
    gross_losses: Decimal = ZERO

    @property
    def net(self) -> Decimal:
        return self.gross_gains - self.gross_losses


@dataclass
class TaxBucket:
    term: str
    rate: Decimal | None
    legal_reference: str | None
    gross_gains: Decimal = ZERO
    loss_set_off: Decimal = ZERO
    exemption_applied: Decimal = ZERO
    basic_exemption_applied: Decimal = ZERO
    taxable: Decimal = ZERO
    base_tax: Decimal = ZERO
    surcharge_rate: Decimal = ZERO
    surcharge: Decimal = ZERO
    cess_rate: Decimal = ZERO
    cess: Decimal = ZERO
    lines: list[GainLine] = field(default_factory=list, repr=False)
    rule: TaxRuleSpec | None = field(default=None, repr=False)
    remaining: Decimal = field(default=ZERO, repr=False)

    @property
    def total_tax(self) -> Decimal:
        return self.base_tax + self.surcharge + self.cess

    @property
    def after_set_off(self) -> Decimal:
        return self.gross_gains - self.loss_set_off

    @property
    def key(self) -> str:
        return f"{self.term}@{pct(self.rate)}"


@dataclass
class CarryForward:
    stcl: Decimal = ZERO
    ltcl: Decimal = ZERO
    speculative_loss: Decimal = ZERO
    notes: list[str] = field(default_factory=list)


@dataclass
class LineTax:
    line_id: str
    symbol: str
    term: str
    capital_gain: Decimal
    estimated_tax: Decimal


@dataclass
class TaxYearResult:
    tax_year: str
    rule_set_version: str
    status: str  # complete | incomplete
    incomplete_reasons: list[str]
    message: str | None
    totals: dict[str, TermTotals]
    set_off_log: list[str]
    exemption_limit: Decimal
    exemption_used: Decimal
    basic_exemption_used: Decimal
    buckets: list[TaxBucket]
    base_tax: Decimal
    surcharge: Decimal
    cess: Decimal
    total_tax_estimate: Decimal
    effective_rate: Decimal | None
    carry_forward: CarryForward
    total_income_for_surcharge: Decimal
    lines: list[GainLine] = field(default_factory=list, repr=False)
    notes: list[str] = field(default_factory=list)
    label: str = ESTIMATED
    is_estimate: bool = True
    disclaimer: str = DISCLAIMER

    @property
    def taxable_by_bucket(self) -> dict[str, Decimal]:
        return {b.key: b.taxable for b in self.buckets}

    @property
    def tax_by_bucket(self) -> dict[str, Decimal]:
        return {b.key: b.total_tax for b in self.buckets}

    def allocate_to_lines(self) -> list[LineTax]:
        """Apportion the total estimated tax to gain lines, pro-rata to each line's positive gain within its
        (term, rate) bucket. Loss lines get 0. Rounded to paise; the rounding residual goes to the line with the
        largest allocation so the allocations sum exactly to ``money(total_tax_estimate)``."""
        raw: dict[str, Decimal] = {line.line_id: ZERO for line in self.lines}
        for bucket in self.buckets:
            weight = sum((ln.capital_gain for ln in bucket.lines if ln.capital_gain > 0), ZERO)
            if weight <= 0 or bucket.total_tax == 0:
                continue
            for ln in bucket.lines:
                if ln.capital_gain > 0:
                    raw[ln.line_id] += bucket.total_tax * ln.capital_gain / weight
        rounded = {k: money(v) for k, v in raw.items()}
        diff = money(self.total_tax_estimate) - sum(rounded.values(), ZERO)
        if diff != 0 and raw:
            biggest = max(raw, key=lambda k: raw[k])
            rounded[biggest] += diff
        return [
            LineTax(ln.line_id, ln.symbol, ln.term, ln.capital_gain, rounded[ln.line_id]) for ln in self.lines
        ]

    def to_dict(self) -> dict[str, Any]:
        out = jsonable(self)
        out["totals"] = {
            k: {"gross_gains": str(money(v.gross_gains)), "gross_losses": str(money(v.gross_losses)),
                "net": str(money(v.net))}
            for k, v in self.totals.items()
        }
        out["buckets"] = [
            {**jsonable(b), "key": b.key, "after_set_off": str(money(b.after_set_off)),
             "total_tax": str(money(b.total_tax))}
            for b in self.buckets
        ]
        return out


def _sorted_desc(buckets: Iterable[TaxBucket]) -> list[TaxBucket]:
    return sorted(buckets, key=lambda b: b.rate if b.rate is not None else ZERO, reverse=True)


def _absorb(amount: Decimal, buckets: Sequence[TaxBucket], what: str, log: list[str], attr: str) -> Decimal:
    """Reduce bucket.remaining (highest rate first) by up to ``amount``; returns the unabsorbed amount."""
    left = amount
    for b in _sorted_desc(buckets):
        if left <= 0:
            break
        if b.remaining <= 0:
            continue
        used = min(left, b.remaining)
        b.remaining -= used
        setattr(b, attr, getattr(b, attr) + used)
        left -= used
        log.append(f"Set off {inr(used)} {what} against {b.term} @ {pct(b.rate)} ({inr(b.remaining)} left).")
    return left


def compute_tax_year(
    gains: Iterable[GainLine], tax_year: str, profile: TaxProfileIn, rulebook: RuleBook
) -> TaxYearResult:
    tax_year_bounds(tax_year)  # validates format
    all_lines = list(gains)
    lines = [g for g in all_lines if g.tax_year == tax_year]
    reasons: list[str] = []
    notes: list[str] = []
    log: list[str] = []
    if len(lines) != len(all_lines):
        notes.append(f"{len(all_lines) - len(lines)} gain line(s) from other tax years ignored.")
    for g in lines:
        reasons.extend(g.incomplete_reasons)

    totals = {t: TermTotals() for t in TERMS}
    buckets: dict[tuple[str, Decimal | None], TaxBucket] = {}
    losses = {"STCG": ZERO, "LTCG": ZERO}
    spec_lines: list[GainLine] = []
    for g in lines:
        if g.term not in TERMS:
            continue  # unclassified: already flagged
        if g.capital_gain >= 0:
            totals[g.term].gross_gains += g.capital_gain
        else:
            totals[g.term].gross_losses += -g.capital_gain
        if g.term == "SPEC":
            spec_lines.append(g)
            continue
        if g.capital_gain > 0:
            if g.rate is None:
                continue  # rule missing: flagged on the line
            key = (g.term, g.rate)
            if key not in buckets:
                buckets[key] = TaxBucket(term=g.term, rate=g.rate, legal_reference=g.legal_reference, rule=g.rule)
            b = buckets[key]
            b.gross_gains += g.capital_gain
            b.remaining += g.capital_gain
            b.lines.append(g)
        elif g.capital_gain < 0:
            losses[g.term] += -g.capital_gain

    st_b = [b for b in buckets.values() if b.term == "STCG"]
    lt_b = [b for b in buckets.values() if b.term == "LTCG"]

    # 1) current-year set-off
    stcl_left = losses["STCG"]
    ltcl_left = losses["LTCG"]
    if stcl_left:
        log.append(f"Current-year short-term capital loss: {inr(stcl_left)}.")
        stcl_left = _absorb(stcl_left, st_b, "current-year STCL", log, "loss_set_off")
    if ltcl_left:
        log.append(f"Current-year long-term capital loss: {inr(ltcl_left)} (can only offset LTCG).")
        ltcl_left = _absorb(ltcl_left, lt_b, "current-year LTCL", log, "loss_set_off")
    if stcl_left:
        stcl_left = _absorb(stcl_left, lt_b, "remaining current-year STCL", log, "loss_set_off")

    # 2) brought-forward losses
    bf_stcl = D(profile.carried_forward_stcl) if profile.carried_forward_stcl is not None else ZERO
    bf_ltcl = D(profile.carried_forward_ltcl) if profile.carried_forward_ltcl is not None else ZERO
    if profile.carried_forward_stcl is None or profile.carried_forward_ltcl is None:
        notes.append("Brought-forward capital losses not provided; assumed nil.")
    if bf_stcl:
        log.append(f"Brought-forward STCL available: {inr(bf_stcl)}.")
        bf_stcl = _absorb(bf_stcl, st_b, "brought-forward STCL", log, "loss_set_off")
    if bf_ltcl:
        log.append(f"Brought-forward LTCL available: {inr(bf_ltcl)} (can only offset LTCG).")
        bf_ltcl = _absorb(bf_ltcl, lt_b, "brought-forward LTCL", log, "loss_set_off")
    if bf_stcl:
        bf_stcl = _absorb(bf_stcl, lt_b, "remaining brought-forward STCL", log, "loss_set_off")

    net_stcg = sum((b.remaining for b in st_b), ZERO)
    net_ltcg = sum((b.remaining for b in lt_b), ZERO)

    # 3) LTCG exemption, once per tax year, per asset type (s.112A / s.198)
    exemption_limit = ZERO
    exemption_used = ZERO
    for asset in sorted({b.lines[0].asset_type for b in lt_b}):
        limit = rulebook.exemption_for_tax_year(asset, tax_year)
        exemption_limit += limit
        if limit > 0:
            group = [b for b in lt_b if b.lines[0].asset_type == asset]
            before = sum((b.remaining for b in group), ZERO)
            if before > 0:
                log.append(
                    f"LTCG exemption for {tax_year}: {inr(limit)} applied once, highest-rate LTCG bucket first."
                )
            _absorb(limit, group, "LTCG exemption", log, "exemption_applied")
            exemption_used += before - sum((b.remaining for b in group), ZERO)
    if not lt_b:
        exemption_limit = rulebook.exemption_for_tax_year(LISTED_EQUITY, tax_year)

    # 4) speculative income (net within the year; only speculative losses offset it)
    spec_net = totals["SPEC"].net
    bf_spec = D(profile.carried_forward_speculative) if profile.carried_forward_speculative is not None else ZERO
    spec_taxable = ZERO
    spec_cf = bf_spec
    spec_bucket: TaxBucket | None = None
    if spec_lines:
        log.append(f"Net speculative (intraday) income for the year: {inr(spec_net)}.")
    if spec_net > 0:
        used = min(spec_net, bf_spec)
        if used:
            log.append(f"Set off {inr(used)} brought-forward speculative loss against speculative income.")
        spec_taxable = spec_net - used
        spec_cf = bf_spec - used
    elif spec_net < 0:
        spec_cf = bf_spec - spec_net
        log.append(f"Speculative loss {inr(-spec_net)} can only offset speculative income; carried forward.")
    if spec_taxable > 0:
        spec_rule = next((ln.rule for ln in spec_lines if ln.rule is not None), None)
        spec_rate = profile.slab_rate_for_business_income
        spec_bucket = TaxBucket(
            term="SPEC", rate=D(spec_rate) if spec_rate is not None else None,
            legal_reference=spec_rule.legal_reference if spec_rule else None, rule=spec_rule,
            gross_gains=totals["SPEC"].gross_gains,
            loss_set_off=totals["SPEC"].gross_losses + (spec_net - spec_taxable),
        )
        spec_bucket.remaining = spec_taxable
        spec_bucket.lines = [ln for ln in spec_lines if ln.capital_gain > 0]
        if spec_rate is None:
            reasons.append(
                "Slab rate for business income not provided — intraday (speculative) income of "
                f"{inr(spec_taxable)} is taxed at your slab rate; its tax is excluded from this estimate."
            )

    # 5) basic-exemption-limit shortfall (residents only)
    regime = profile.regime
    if regime is None:
        regime = "new"
        if net_stcg + net_ltcg + spec_taxable > 0:
            reasons.append("Tax regime not provided; new regime (default) assumed.")
    other = D(profile.other_taxable_income) if profile.other_taxable_income is not None else None
    basic_used = ZERO
    special_remaining = sum((b.remaining for b in st_b + lt_b), ZERO)
    if special_remaining > 0:
        residency = (profile.residency or "").lower() or None
        if residency is None:
            reasons.append(
                "Residency not provided — residents may adjust unused basic exemption limit against STCG/LTCG, "
                "which could reduce tax."
            )
        elif residency == "resident":
            bel = rulebook.basic_exemption_limit(regime, tax_year)
            if other is None:
                reasons.append(
                    "Other taxable income not provided — if it is below the basic exemption limit, the shortfall "
                    "could reduce tax on STCG/LTCG."
                )
            elif bel.limit is None:
                reasons.append(f"Basic exemption limit for {regime} regime in {tax_year} not configured.")
            else:
                shortfall = bel.limit - other - spec_taxable
                if bel.age_dependent and bel.max_age_dependent_limit is not None and (
                    other + spec_taxable < bel.max_age_dependent_limit
                ):
                    reasons.append(
                        f"Basic exemption limit under the {regime} regime depends on age; "
                        f"{inr(bel.limit)} assumed. {bel.notes or ''}".strip()
                    )
                if shortfall > 0:
                    log.append(
                        f"Basic exemption limit {inr(bel.limit)} ({regime} regime): shortfall {inr(shortfall)} "
                        "adjusted against STCG/LTCG (resident), highest rate first."
                    )
                    before = special_remaining
                    _absorb(shortfall, st_b + lt_b, "basic exemption shortfall", log, "basic_exemption_applied")
                    basic_used = before - sum((b.remaining for b in st_b + lt_b), ZERO)
        else:
            notes.append("Basic exemption shortfall adjustment against STCG/LTCG is available to residents only.")

    # 6) base tax
    all_buckets = _sorted_desc(st_b) + _sorted_desc(lt_b) + ([spec_bucket] if spec_bucket else [])
    for b in all_buckets:
        b.taxable = b.remaining
        b.base_tax = b.taxable * b.rate if b.rate is not None else ZERO
    base_tax = sum((b.base_tax for b in all_buckets), ZERO)

    # 7) surcharge + cess
    total_income = (other or ZERO) + net_stcg + net_ltcg + spec_taxable
    if other is None and (base_tax > 0 or spec_taxable > 0):
        reasons.append(
            "Other taxable income not provided — surcharge depends on total income; computed assuming no other "
            "income (may be understated)."
        )
    regime_cap = rulebook.regime_surcharge_cap(regime)
    for b in all_buckets:
        if b.rule is None or b.base_tax == 0:
            b.cess_rate = b.rule.cess_rate if b.rule is not None else ZERO
            continue
        rate = b.rule.surcharge_rate_for(total_income)
        if b.rule.surcharge_cap is not None:
            rate = min(rate, b.rule.surcharge_cap)
        if regime_cap is not None:
            rate = min(rate, regime_cap)
        b.surcharge_rate = rate
        b.surcharge = b.base_tax * rate
        b.cess_rate = b.rule.cess_rate
        b.cess = (b.base_tax + b.surcharge) * b.cess_rate
    surcharge = sum((b.surcharge for b in all_buckets), ZERO)
    cess = sum((b.cess for b in all_buckets), ZERO)
    if surcharge > 0:
        log.append(
            f"Surcharge on total income {inr(total_income)}: {inr(surcharge)} "
            "(capped at 15% on STCG/LTCG; marginal relief not computed)."
        )
    if cess > 0:
        log.append(f"Health & education cess on tax + surcharge: {inr(cess)}.")
    total_tax = base_tax + surcharge + cess
    taxable_income = net_stcg + net_ltcg + spec_taxable
    effective_rate = (total_tax / taxable_income) if taxable_income > 0 else None

    # 8) carry-forward
    cf = CarryForward(stcl=stcl_left + bf_stcl, ltcl=ltcl_left + bf_ltcl, speculative_loss=spec_cf)
    if cf.stcl or cf.ltcl:
        cf.notes.append(
            "Capital losses can be carried forward for 8 tax years (STCL offsets STCG/LTCG; LTCL offsets LTCG "
            "only), provided the return is filed by the due date."
        )
        log.append(f"Carry forward: STCL {inr(cf.stcl)}, LTCL {inr(cf.ltcl)}.")
    if cf.speculative_loss:
        cf.notes.append(
            "Speculative losses can be carried forward for 4 tax years and only offset speculative income; "
            "the return must be filed by the due date."
        )
        log.append(f"Carry forward speculative loss: {inr(cf.speculative_loss)}.")
    if (profile.residency or "").lower() == "nri":
        notes.append("NRIs: TDS applies on capital gains; DTAA relief not modelled.")
    notes.append("Rebate u/s 87A, marginal relief and rounding of income/tax are not modelled.")

    reasons = dedupe(reasons)
    status = "incomplete" if reasons else "complete"
    return TaxYearResult(
        tax_year=tax_year,
        rule_set_version=rulebook.version,
        status=status,
        incomplete_reasons=reasons,
        message=INCOMPLETE_MESSAGE if reasons else None,
        totals=totals,
        set_off_log=log,
        exemption_limit=exemption_limit,
        exemption_used=exemption_used,
        basic_exemption_used=basic_used,
        buckets=all_buckets,
        base_tax=base_tax,
        surcharge=surcharge,
        cess=cess,
        total_tax_estimate=total_tax,
        effective_rate=effective_rate,
        carry_forward=cf,
        total_income_for_surcharge=total_income,
        lines=lines,
        notes=dedupe(notes),
    )


def compute_tax_years(
    gains: Iterable[GainLine],
    profile: TaxProfileIn,
    rulebook: RuleBook,
    *,
    profiles_by_year: dict[str, TaxProfileIn] | None = None,
) -> list[TaxYearResult]:
    """Compute every tax year present in ``gains`` in order, chaining carried-forward losses.

    ``profile``'s brought-forward losses apply to the first year; later years receive the previous year's
    carry-forward. ``profiles_by_year`` can supply year-specific other income / slab rate. Carry-forward expiry
    (8 / 4 years) is not tracked.
    """
    lines = list(gains)
    years = sorted({g.tax_year for g in lines})
    results: list[TaxYearResult] = []
    cf: CarryForward | None = None
    for ty in years:
        base = (profiles_by_year or {}).get(ty, profile)
        if cf is not None:
            base = replace(base, carried_forward_stcl=cf.stcl, carried_forward_ltcl=cf.ltcl,
                           carried_forward_speculative=cf.speculative_loss)
        res = compute_tax_year(lines, ty, base, rulebook)
        results.append(res)
        cf = res.carry_forward
    return results


# --------------------------------------------------------------------------------------------------------------
# Hypothetical sales (unrealized estimate / harvesting)
# --------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class OpenLotPrice:
    lot: Lot
    ltp: Decimal


@dataclass
class RealizedContext:
    lines: list[GainLine] = field(default_factory=list)
    profile: TaxProfileIn = field(default_factory=TaxProfileIn)


def _as_lot_price(item: OpenLotPrice | tuple[Lot, Decimal]) -> OpenLotPrice:
    if isinstance(item, OpenLotPrice):
        return item
    lot, ltp = item
    return OpenLotPrice(lot, D(ltp))


def hypothetical_sale_lines(
    open_lots_with_ltp: Iterable[OpenLotPrice | tuple[Lot, Decimal]],
    as_of: date,
    rulebook: RuleBook,
    charges_engine: Any | None = None,
) -> tuple[list[GainLine], list[str]]:
    """Gain lines as if every given open lot were sold at its LTP on ``as_of``.

    With a ``charges_engine`` (``app.tax.charges.ChargesEngine``) one delivery sell per symbol is costed and its
    charges/STT allocated pro-rata by quantity; otherwise sell charges are taken as nil (noted).
    """
    items = [_as_lot_price(i) for i in open_lots_with_ltp if _as_lot_price(i).lot.remaining_quantity > 0]
    notes: list[str] = []
    by_symbol: dict[str, list[OpenLotPrice]] = {}
    for it in items:
        by_symbol.setdefault(it.lot.symbol, []).append(it)
    lines: list[GainLine] = []
    if charges_engine is None and items:
        notes.append("Sell-side charges for the hypothetical sale not estimated (no charge schedule supplied).")
    for symbol, group in by_symbol.items():
        qty = sum((g.lot.remaining_quantity for g in group), ZERO)
        turnover = sum((g.lot.remaining_quantity * g.ltp for g in group), ZERO)
        sell_charges = sell_stt = ZERO
        if charges_engine is not None and qty > 0:
            bd = charges_engine.compute("equity_delivery", "SELL", qty, turnover / qty, trade_date=as_of)
            sell_charges, sell_stt = bd.total, bd.stt
        for g in group:
            lot = g.lot
            share = lot.remaining_quantity / qty
            m = Match(
                lot_id=lot.lot_id,
                buy_txn_id=lot.buy_txn_id,
                sell_txn_id=f"HYPOTHETICAL:{as_of.isoformat()}",
                symbol=symbol,
                segment="delivery",
                quantity=lot.remaining_quantity,
                acquired_date=lot.acquired_date,
                sold_date=as_of,
                cost_per_share=lot.cost_per_share,
                sell_price=g.ltp,
                purchase_value=lot.remaining_quantity * lot.cost_per_share,
                sale_value=lot.remaining_quantity * g.ltp,
                buy_charges_alloc=lot.buy_charges,
                sell_charges_alloc=sell_charges * share,
                buy_stt_alloc=lot.buy_stt,
                sell_stt_alloc=sell_stt * share,
                holding_days=(as_of - lot.acquired_date).days,
                is_bonus=lot.is_bonus,
                fmv_31jan2018=lot.fmv_31jan2018,
            )
            lines.append(capital_gain_for_match(m, rulebook, is_hypothetical=True))
    return lines, notes


@dataclass
class UnrealizedLotEstimate:
    lot_id: str
    symbol: str
    quantity: Decimal
    acquired_date: date
    holding_days: int
    term: str
    rate: Decimal | None
    cost_of_acquisition: Decimal
    market_value: Decimal
    unrealized_gain: Decimal  # tax view (STT not deducted)
    unrealized_pnl: Decimal  # after all charges


@dataclass
class UnrealizedTaxEstimate:
    as_of: date
    tax_year: str
    lots: list[UnrealizedLotEstimate]
    total_unrealized_gain: Decimal
    estimated_tax_if_sold: Decimal  # incremental over realized gains this tax year
    status: str
    incomplete_reasons: list[str]
    message: str | None
    rule_set_version: str
    notes: list[str] = field(default_factory=list)
    informational_note: str = UNREALIZED_LABEL
    label: str = ESTIMATED
    is_estimate: bool = True
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


def unrealized_tax_estimate(
    open_lots_with_ltp: Iterable[OpenLotPrice | tuple[Lot, Decimal]],
    as_of: date,
    rulebook: RuleBook,
    realized_context: RealizedContext | None = None,
    *,
    charges_engine: Any | None = None,
) -> UnrealizedTaxEstimate:
    """Informational: extra tax this tax year if all given lots were sold on ``as_of`` at LTP
    (= tax(realized + hypothetical) - tax(realized), so set-offs/exemption already used are respected)."""
    ctx = realized_context or RealizedContext()
    ty = tax_year_of(as_of)
    hyp, notes = hypothetical_sale_lines(open_lots_with_ltp, as_of, rulebook, charges_engine)
    realized = [ln for ln in ctx.lines if ln.tax_year == ty]
    without = compute_tax_year(realized, ty, ctx.profile, rulebook)
    with_sale = compute_tax_year(realized + hyp, ty, ctx.profile, rulebook)
    reasons = dedupe(with_sale.incomplete_reasons)
    lots = [
        UnrealizedLotEstimate(
            lot_id=ln.lot_id, symbol=ln.symbol, quantity=ln.quantity, acquired_date=ln.acquired_date,
            holding_days=ln.holding_days, term=ln.term, rate=ln.rate, cost_of_acquisition=ln.cost_of_acquisition,
            market_value=ln.sale_value, unrealized_gain=ln.capital_gain, unrealized_pnl=ln.trading_pnl,
        )
        for ln in hyp
    ]
    return UnrealizedTaxEstimate(
        as_of=as_of,
        tax_year=ty,
        lots=lots,
        total_unrealized_gain=sum((ln.capital_gain for ln in hyp), ZERO),
        estimated_tax_if_sold=with_sale.total_tax_estimate - without.total_tax_estimate,
        status="incomplete" if reasons else "complete",
        incomplete_reasons=reasons,
        message=INCOMPLETE_MESSAGE if reasons else None,
        rule_set_version=rulebook.version,
        notes=notes,
    )


# --------------------------------------------------------------------------------------------------------------
# Net P&L
# --------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class NetPnL:
    gross_pnl: Decimal
    charges: Decimal
    pnl_before_tax: Decimal
    estimated_tax: Decimal | None
    net_after_tax: Decimal | None
    label: str = ESTIMATED
    is_estimate: bool = True
    note: str | None = None

    def rounded(self) -> NetPnL:
        def r(v: Decimal | None) -> Decimal | None:
            return None if v is None else money(v)

        return replace(
            self, gross_pnl=money(self.gross_pnl), charges=money(self.charges),
            pnl_before_tax=money(self.pnl_before_tax), estimated_tax=r(self.estimated_tax),
            net_after_tax=r(self.net_after_tax),
        )


def net_pnl(gross: Decimal, charges_total: Decimal, est_tax: Decimal | None) -> NetPnL:
    """Gross -> after charges -> after estimated tax. Gross is always reported; tax None => net None."""
    gross_d, charges_d = D(gross), D(charges_total)
    before_tax = gross_d - charges_d
    if est_tax is None:
        return NetPnL(gross_d, charges_d, before_tax, None, None,
                      note="Estimated tax unavailable; net after tax not computed.")
    tax_d = D(est_tax)
    return NetPnL(gross_d, charges_d, before_tax, tax_d, before_tax - tax_d)
