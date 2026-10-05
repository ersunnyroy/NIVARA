"""Dated tax rules (mirrors ``models.tax.TaxRule``) and the :class:`RuleBook` that looks them up.

Rules are keyed by *date of transfer* (``effective_from <= sold_date <= effective_to``). Rates are fractions.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.tax.common import ZERO, D, D_opt, parse_date, tax_year_bounds


class RuleNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class TaxRuleSpec:
    rule_set_version: str
    asset_type: str
    term: str  # STCG | LTCG | SPEC
    effective_from: date
    effective_to: date | None = None
    holding_period_months: int = 12
    rate: Decimal | None = None  # None => slab rate (needs user input)
    exemption_threshold: Decimal | None = None  # per tax year
    surcharge_cap: Decimal | None = None
    surcharge_slabs: list[dict[str, Decimal]] = field(default_factory=list)  # [{"above": D, "rate": D}]
    cess_rate: Decimal = Decimal("0.04")
    grandfather_date: date | None = None
    legal_reference: str | None = None
    source_url: str | None = None
    notes: str | None = None
    transaction_type: str = "transfer"
    tax_years: str | None = None

    _FIELDS = (
        "rule_set_version", "asset_type", "term", "effective_from", "effective_to", "holding_period_months",
        "rate", "exemption_threshold", "surcharge_cap", "surcharge_slabs", "cess_rate", "grandfather_date",
        "legal_reference", "source_url", "notes", "transaction_type", "tax_years",
    )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TaxRuleSpec:
        eff_from = parse_date(data.get("effective_from"))
        if eff_from is None:
            raise ValueError("Tax rule requires effective_from")
        slabs = [
            {"above": D(s["above"]), "rate": D(s["rate"])}
            for s in (data.get("surcharge_slabs") or [])
        ]
        slabs.sort(key=lambda s: s["above"])
        cess = data.get("cess_rate")
        return cls(
            rule_set_version=str(data["rule_set_version"]),
            asset_type=str(data["asset_type"]),
            term=str(data["term"]).upper(),
            effective_from=eff_from,
            effective_to=parse_date(data.get("effective_to")),
            holding_period_months=int(data.get("holding_period_months") or 12),
            rate=D_opt(data.get("rate")),
            exemption_threshold=D_opt(data.get("exemption_threshold")),
            surcharge_cap=D_opt(data.get("surcharge_cap")),
            surcharge_slabs=slabs,
            cess_rate=D(cess) if cess is not None else Decimal("0.04"),
            grandfather_date=parse_date(data.get("grandfather_date")),
            legal_reference=data.get("legal_reference"),
            source_url=data.get("source_url"),
            notes=data.get("notes"),
            transaction_type=str(data.get("transaction_type") or "transfer"),
            tax_years=data.get("tax_years"),
        )

    @classmethod
    def coerce(cls, value: TaxRuleSpec | Mapping[str, Any] | Any) -> TaxRuleSpec:
        if isinstance(value, TaxRuleSpec):
            return value
        if isinstance(value, Mapping):
            return cls.from_dict(value)
        return cls.from_dict({k: getattr(value, k, None) for k in cls._FIELDS})  # ORM TaxRule row

    def covers(self, d: date) -> bool:
        return self.effective_from <= d and (self.effective_to is None or d <= self.effective_to)

    def surcharge_rate_for(self, total_income: Decimal) -> Decimal:
        """Highest slab rate whose threshold total income exceeds (before any cap)."""
        rate = ZERO
        for slab in self.surcharge_slabs:
            if total_income > slab["above"]:
                rate = slab["rate"]
        return rate


@dataclass(frozen=True)
class BasicExemption:
    limit: Decimal | None
    age_dependent: bool = False
    max_age_dependent_limit: Decimal | None = None
    notes: str | None = None


def _ty_start(tax_year: str) -> int:
    return tax_year_bounds(tax_year)[0].year


class RuleBook:
    """Look-up over a set of dated rules (one rule-set version)."""

    def __init__(
        self,
        rules: Iterable[TaxRuleSpec | Mapping[str, Any]],
        *,
        exemption_limits: Mapping[str, Any] | None = None,
        regime_surcharge_caps: Mapping[str, Any] | None = None,
        version: str | None = None,
    ) -> None:
        specs = [TaxRuleSpec.coerce(r) for r in rules]
        if not specs:
            raise ValueError("RuleBook needs at least one rule")
        versions = sorted({r.rule_set_version for r in specs})
        self._version = version or versions[-1]
        self.rules = [r for r in specs if r.rule_set_version == self._version]
        if not self.rules:
            raise ValueError(f"No rules for rule_set_version {self._version!r}")
        self.exemption_limits = dict(exemption_limits or {})
        self.regime_surcharge_caps = {k: D_opt(v) for k, v in (regime_surcharge_caps or {}).items()}

    @classmethod
    def default(cls) -> RuleBook:
        from app.tax.defaults import (
            basic_exemption_limits,
            default_tax_rules,
            regime_surcharge_caps,
        )

        return cls(
            default_tax_rules(),
            exemption_limits=basic_exemption_limits(),
            regime_surcharge_caps=regime_surcharge_caps(),
        )

    @property
    def version(self) -> str:
        return self._version

    def find_rule(self, asset_type: str, term: str, transfer_date: date) -> TaxRuleSpec | None:
        matches = [
            r for r in self.rules
            if r.asset_type == asset_type and r.term == term.upper() and r.covers(transfer_date)
        ]
        return max(matches, key=lambda r: r.effective_from) if matches else None

    def rule_for(self, asset_type: str, term: str, transfer_date: date) -> TaxRuleSpec:
        rule = self.find_rule(asset_type, term, transfer_date)
        if rule is None:
            raise RuleNotFoundError(
                f"No {term} rule for asset type {asset_type!r} on {transfer_date.isoformat()} "
                f"in rule set {self.version}"
            )
        return rule

    def holding_period_months(self, asset_type: str, transfer_date: date) -> int:
        """Holding period that separates short- from long-term, taken from the rules effective on the date."""
        for term in ("LTCG", "STCG"):
            rule = self.find_rule(asset_type, term, transfer_date)
            if rule is not None:
                return rule.holding_period_months
        raise RuleNotFoundError(
            f"No capital-gains rule for asset type {asset_type!r} on {transfer_date.isoformat()}"
        )

    def exemption_for_tax_year(self, asset_type: str, tax_year: str) -> Decimal:
        """LTCG exemption threshold for a tax year.

        Uses the LTCG rule effective on the *last day* of the tax year. Hence FY 2024-25 gets Rs 1,25,000 for the
        whole year (Finance (No.2) Act 2024 raised the s.112A limit for the entire FY even though the rate change
        applies only to transfers on/after 23-Jul-2024).
        """
        _, end = tax_year_bounds(tax_year)
        rule = self.find_rule(asset_type, "LTCG", end)
        if rule is None or rule.exemption_threshold is None:
            return ZERO
        return rule.exemption_threshold

    def basic_exemption_limit(self, regime: str, tax_year: str) -> BasicExemption:
        start = _ty_start(tax_year)
        for entry in self.exemption_limits.get(regime, []) or []:
            lo = _ty_start(entry["from_tax_year"])
            hi = _ty_start(entry["to_tax_year"]) if entry.get("to_tax_year") else None
            if lo <= start and (hi is None or start <= hi):
                return BasicExemption(
                    limit=D(entry["limit"]),
                    age_dependent=bool(entry.get("age_dependent", False)),
                    max_age_dependent_limit=D_opt(entry.get("max_age_dependent_limit")),
                    notes=entry.get("notes"),
                )
        return BasicExemption(limit=None)

    def regime_surcharge_cap(self, regime: str | None) -> Decimal | None:
        if regime is None:
            return None
        return self.regime_surcharge_caps.get(regime)
