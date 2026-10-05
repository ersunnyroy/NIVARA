"""Idempotent seeding of reference data: exchanges, sectors, data-source registry, model versions,
dated tax rules and charge schedules. Contains configuration only — never market data."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.config import DEFAULTS, LEVELS_VERSION, MODEL_VERSION, REGIME_VERSION, SCORING_VERSION
from app.analytics.sector import INDUSTRY_TO_INDEX
from app.core.timeutil import utcnow
from app.models import ChargeSchedule, DataSource, Exchange, ModelVersion, Sector, TaxRule
from app.technical.indicators import INDICATOR_VERSION

NSE_TERMS = ("Official NSE public archives/website endpoints. Low request rate with on-disk caching; "
             "personal research use. Review NSE terms of use before any redistribution or commercial use.")

DATA_SOURCES = [
    # key, name, kind, provider, sla minutes, requires credentials
    ("nse_securities", "NSE equity master (EQUITY_L)", "reference", "NSE archives", 7 * 24 * 60, False),
    ("nse_index_constituents", "NIFTY index constituents", "reference", "NSE / niftyindices", 7 * 24 * 60, False),
    ("nse_cm_bhavcopy", "NSE CM bhavcopy + delivery (EOD)", "market_data", "NSE archives", 30 * 60, False),
    ("nse_indices", "NSE index closes incl. India VIX (EOD)", "market_data", "NSE archives", 30 * 60, False),
    ("nse_fo_bhavcopy", "NSE F&O bhavcopy (EOD)", "fno", "NSE archives", 30 * 60, False),
    ("nse_flows", "FII/DII provisional cash flows", "flows", "NSE website", 30 * 60, False),
    ("nse_corporate_actions", "Corporate actions", "corporate_actions", "NSE website", 3 * 24 * 60, False),
    ("nse_event_calendar", "Board meetings / results calendar", "corporate_actions", "NSE website", 3 * 24 * 60, False),
    ("nse_results", "Financial results (XBRL)", "fundamentals", "NSE website/archives", 7 * 24 * 60, False),
    ("nse_shareholding", "Shareholding pattern", "fundamentals", "NSE website", 30 * 24 * 60, False),
    ("nse_announcements", "Corporate announcements (RSS)", "news", "NSE archives RSS", 6 * 60, False),
    ("nse_holidays", "Trading holidays", "calendar", "NSE website", 30 * 24 * 60, False),
    ("rss_secondary", "Configured secondary news RSS feeds", "news", "Configured feeds", 6 * 60, False),
    ("upstox_quotes", "Upstox live quotes (optional)", "market_data", "Upstox API v2", 5, True),
    ("kite_quotes", "Zerodha Kite live quotes (optional)", "market_data", "Kite Connect v3", 5, True),
    ("anthropic_ai", "AI explanations (Claude)", "ai", "Anthropic API", 24 * 60, True),
]


def seed_reference(db: Session) -> dict:
    created = {"exchanges": 0, "sectors": 0, "data_sources": 0, "model_versions": 0, "tax_rules": 0, "charges": 0}
    for code, name in (("NSE", "National Stock Exchange of India"), ("BSE", "BSE Limited")):
        if db.get(Exchange, code) is None:
            db.add(Exchange(code=code, name=name))
            created["exchanges"] += 1
    existing = {s.name for s in db.scalars(select(Sector))}
    for industry, idx in INDUSTRY_TO_INDEX.items():
        if industry not in existing:
            db.add(Sector(name=industry, index_name=idx))
            created["sectors"] += 1
    have = {d.key for d in db.scalars(select(DataSource))}
    for key, name, kind, provider, sla, creds in DATA_SOURCES:
        if key not in have:
            db.add(DataSource(key=key, name=name, kind=kind, provider=provider, freshness_sla_minutes=sla,
                              requires_credentials=creds, is_enabled=not creds,
                              terms_note=NSE_TERMS if provider.startswith("NSE") else None))
            created["data_sources"] += 1
    versions = [("model", MODEL_VERSION, {}), ("scoring", SCORING_VERSION, {"weights": DEFAULTS["scoring_weights"]}),
                ("indicators", INDICATOR_VERSION, {}), ("levels", LEVELS_VERSION, {"risk": DEFAULTS["risk_limits"]}),
                ("regime", REGIME_VERSION, DEFAULTS["regime"])]
    have_v = {(m.component, m.version) for m in db.scalars(select(ModelVersion))}
    for comp, ver, params in versions:
        if (comp, ver) not in have_v:
            db.add(ModelVersion(component=comp, version=ver, params=params, created_at=utcnow()))
            created["model_versions"] += 1
    created.update(seed_tax_and_charges(db))
    db.commit()
    return created


def seed_tax_and_charges(db: Session) -> dict:
    from app.tax.defaults import default_charge_schedules, default_tax_rules

    out = {"tax_rules": 0, "charges": 0}
    if db.scalar(select(TaxRule).limit(1)) is None:
        for r in default_tax_rules():
            db.add(TaxRule(**_model_fields(TaxRule, r), created_at=utcnow()))
            out["tax_rules"] += 1
    if db.scalar(select(ChargeSchedule).limit(1)) is None:
        for c in default_charge_schedules():
            fields = _model_fields(ChargeSchedule, c)
            fields.setdefault("is_default", True)
            db.add(ChargeSchedule(**fields, created_at=utcnow()))
            out["charges"] += 1
    return out


def _model_fields(model, d: dict) -> dict:
    cols = {c.key for c in model.__table__.columns}
    return {k: _jsonable(v) for k, v in d.items() if k in cols and k not in ("id", "created_at")}


def _jsonable(v):

    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v
