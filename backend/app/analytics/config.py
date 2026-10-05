"""Default, admin-overridable analytics configuration.

Stored in `app_settings` under the keys below; `load_config(db)` deep-merges DB overrides on top of
these defaults. Every recommendation snapshot records the effective config/version it used.
"""
from __future__ import annotations

import copy
from typing import Any

MODEL_VERSION = "nivara-model-1.0"
SCORING_VERSION = "score-1.0"
LEVELS_VERSION = "levels-1.0"
REGIME_VERSION = "regime-1.0"

DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 25,
    "momentum": 15,
    "volume": 10,
    "relative_strength": 10,
    "fundamentals": 15,
    "sector": 10,
    "news": 5,
    "fno": 5,
    "risk_reward": 5,
}

DEFAULTS: dict[str, dict[str, Any]] = {
    "scoring_weights": DEFAULT_WEIGHTS,
    "risk_limits": {
        "capital": 1_000_000,
        "risk_per_trade_pct": 1.0,
        "max_risk_pct_per_setup": 8.0,  # reject setups whose stop is further than this from entry
        "min_rr_t2": 1.8,  # minimum reward:risk to Target 2
        "max_single_stock_pct": 20.0,
        "max_sector_pct": 35.0,
        "max_portfolio_risk_pct": 6.0,  # sum of open risk to stops as % of capital
        "atr_stop_multiple": 2.0,
        "min_track_record_for_live": 30,  # closed outcomes before any idea is marked live_consideration
    },
    "exclusions": {
        "min_price": 20.0,  # penny-stock filter (INR)
        "min_avg_turnover_cr": 5.0,  # 20-day average traded value, ₹ crore
        "min_history_days": 220,
        "allowed_series": ["EQ"],
        "exclude_surveillance": True,  # ASM/GSM etc. when flags are available
        "max_abs_gap_pct_unadjusted": 35.0,  # abnormal unexplained moves → unreliable data
        "results_blackout_sessions": 2,  # results within N sessions → WAIT not BUY
        "universe_index": "nifty500",
    },
    "regime": {
        "weights": {
            "nifty_trend": 0.22,
            "banknifty_trend": 0.10,
            "breadth": 0.18,
            "vix": 0.14,
            "momentum": 0.12,
            "sector_participation": 0.12,
            "flows": 0.08,
            "global": 0.04,
        },
        "thresholds": {"strong_bullish": 50, "bullish": 20, "bearish": -20, "strong_bearish": -50},
        "exposure": {"STRONG BULLISH": 90, "BULLISH": 70, "NEUTRAL": 50, "BEARISH": 25, "STRONG BEARISH": 10},
        "max_positions": {"STRONG BULLISH": 10, "BULLISH": 8, "NEUTRAL": 6, "BEARISH": 3, "STRONG BEARISH": 1},
    },
    "scanner": {"top_n": 10, "max_per_sector": 3, "min_score": 55.0},
    "market_hours": {"pre_open": "09:00", "open": "09:15", "close": "15:30", "post_close_data_ready": "18:30"},
    "ai": {"enabled": True, "explain_top_n": 10},
    "notifications": {"in_app": True, "email": False, "webhook": False},
    "tax": {"default_regime": "new"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def merged(key: str, override: dict | None) -> dict:
    return _deep_merge(DEFAULTS[key], override or {})


def load_config(db=None) -> dict[str, dict[str, Any]]:
    """Effective configuration (defaults ⊕ admin overrides)."""
    cfg = copy.deepcopy(DEFAULTS)
    if db is None:
        return cfg
    from app.models import AppSetting

    for row in db.query(AppSetting).all():
        if row.key in cfg:
            cfg[row.key] = _deep_merge(cfg[row.key], row.value)
    return cfg


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    unknown = set(weights) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise ValueError(f"Unknown scoring components: {sorted(unknown)}")
    if any(v < 0 for v in weights.values()):
        raise ValueError("Weights must be non-negative")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Weights must sum to a positive number")
    full = {k: float(weights.get(k, 0.0)) for k in DEFAULT_WEIGHTS}
    # Normalise to 100 so the score stays on a 0-100 scale.
    return {k: round(100.0 * v / total, 4) for k, v in full.items()}
