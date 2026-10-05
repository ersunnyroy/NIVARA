"""AI analysis page: Claude explains the deterministic analysis; it never produces numbers of its own.

Flow: build a structured fact sheet (the only numbers the AI may use) → ask for a JSON explanation with
citations → guardrails flag any number not in the fact sheet and strip certainty language → cache.
Without an API key a deterministic template explanation is returned (status `ai_not_configured`).
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import AIUnavailable, ai_configured, structured_call
from app.ai.guardrails import check_obj, numbers_in
from app.config.settings import get_settings
from app.core.timeutil import utcnow
from app.models import AppSetting, FnoSnapshot, NewsItem, Stock
from app.schemas.dto import j
from app.services.market import latest_regime

PROMPT_VERSION = "analysis-v1"

SYSTEM = """You are the explanation layer of an Indian equity research tool. A quantitative engine has already
computed every number. Your job is to explain that structured data clearly for an individual investor.

Hard rules:
- Use ONLY numbers that appear in the provided FACT SHEET. Never invent prices, targets, ratios, estimates,
  dates, news or company facts. If something is missing, say it is not available.
- Do not change any level (entry, stop, targets) or the score; quantitative risk rules take precedence over you.
- Never promise or imply guaranteed returns or certainty. Use probabilistic language.
- Keep FACT (what the data says) separate from INTERPRETATION (what it may mean). Mark speculation explicitly.
- Every section must be grounded: add citations naming the fact-sheet field you used.
- Be concise: 2-5 sentences per narrative section; bull/bear cases 3-5 bullets each.
This is research and decision support, not investment advice."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["executive_summary", "bull_case", "bear_case", "technical", "fundamental", "news", "fno",
                 "market_context", "entry", "stop", "targets", "risk_reward", "invalidation", "final_score",
                 "citations"],
    "properties": {
        "executive_summary": {"type": "string"},
        "bull_case": {"type": "array", "items": {"type": "string"}},
        "bear_case": {"type": "array", "items": {"type": "string"}},
        "technical": {"type": "string"},
        "fundamental": {"type": "string"},
        "news": {"type": "string"},
        "fno": {"type": "string"},
        "market_context": {"type": "string"},
        "entry": {"type": "string"},
        "stop": {"type": "string"},
        "targets": {"type": "string"},
        "risk_reward": {"type": "string"},
        "invalidation": {"type": "string"},
        "final_score": {"type": "string"},
        "citations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["label", "field"],
            "properties": {"label": {"type": "string"}, "field": {"type": "string"}}}},
    },
}


def fact_sheet(db: Session, stock: Stock) -> dict:
    from app.services.stock_analysis import analyze

    res = analyze(db, stock)
    if res["status"] != "ok":
        return {"status": res["status"], "message": res.get("message")}
    ev = res["evaluation"]
    regime = latest_regime(db)
    news = db.scalars(select(NewsItem).where(NewsItem.stock_id == stock.id).order_by(NewsItem.published_at.desc())
                      .limit(6)).all()
    fno = db.scalar(select(FnoSnapshot).where(FnoSnapshot.underlying == stock.symbol)
                    .order_by(FnoSnapshot.date.desc()).limit(1)) if stock.is_fno else None
    lv = ev.levels.asdict() if ev.levels else None
    fv = res["fundamentals"]
    keep = ("ttm_revenue", "ttm_pat", "ttm_eps", "revenue_growth_yoy", "earnings_growth_yoy", "pe", "peg",
            "ebitda_margin", "pat_margin", "debt_equity", "interest_coverage", "promoter_holding", "promoter_pledge")
    return j({
        "status": "ok", "symbol": stock.symbol, "name": stock.name, "sector": stock.industry, "data_as_of": res["as_of"],
        "price": {"close": ev.cmp, "basis": "official NSE end-of-day close"},
        "indicators": {k: ev.indicators.get(k) for k in ("ema_20", "ema_50", "ema_200", "rsi_14", "macd", "macd_signal",
                                                         "adx", "atr_14", "rel_volume", "delivery_pct", "high_52w",
                                                         "low_52w", "hv_20")},
        "price_action": {"structure": ev.price_action.get("structure"),
                         "supports": ev.price_action.get("supports", [])[:3],
                         "resistances": ev.price_action.get("resistances", [])[:3],
                         "patterns": [k for k, v in ev.price_action.get("patterns", {}).items() if v.get("detected")]},
        "levels": lv, "score": ev.score.breakdown() if ev.score else None, "confidence": ev.confidence,
        "action": ev.action, "rejected": ev.rejected, "rejection_reasons": ev.rejection_reasons,
        "why": ev.why, "why_not": ev.why_not, "invalidation": ev.invalidation,
        "fundamentals": {"score": fv.get("score"), "metrics": {k: v.get("value") for k, v in fv.get("metrics", {}).items()
                                                               if k in keep},
                         "latest_result": (fv.get("result_analysis") or {}).get("summary_text"),
                         "missing": fv.get("missing", [])[:5]},
        "news": [{"date": n.published_at, "headline": n.headline[:200], "event_type": n.event_type,
                  "sentiment": n.sentiment_label, "source": n.source, "verified": n.is_verified} for n in news],
        "fno": None if fno is None else {k: getattr(fno, k) for k in ("date", "pcr_oi", "max_pain", "call_resistance",
                                                                       "put_support", "buildup", "interpretation",
                                                                       "atm_iv", "iv_percentile")},
        "market": None if regime is None else {"regime": regime.regime, "confidence": regime.confidence,
                                               "recommended_exposure_pct": regime.recommended_exposure_pct},
    })


def deterministic(fs: dict) -> dict:
    """Template explanation built only from the fact sheet (used when AI is off or fails)."""
    lv, sc = fs.get("levels") or {}, fs.get("score") or {}
    comps = {c["key"]: c for c in sc.get("components", [])}

    def comp_line(k: str) -> str:
        c = comps.get(k)
        if not c:
            return "Not available."
        if c["fraction"] is None:
            return f"Not available: {c.get('missing_reason') or 'no data'}."
        return f"{c['label']} {c['points']:.1f}/{c['weight']:.0f}. " + " ".join((c["reasons"] + c["cautions"])[:3])

    return {
        "executive_summary": (f"{fs['symbol']} scores {sc.get('total', 0):.1f}/100 with confidence "
                              f"{fs.get('confidence', 0):.0f}/100; engine action: {fs.get('action')}. "
                              + ("Rejected: " + "; ".join(fs["rejection_reasons"]) if fs.get("rejected") else "")),
        "bull_case": fs.get("why", [])[:5] or ["No strong positive factors identified."],
        "bear_case": fs.get("why_not", [])[:5],
        "technical": comp_line("technical") + " " + comp_line("momentum"),
        "fundamental": comp_line("fundamentals"),
        "news": comp_line("news"),
        "fno": comp_line("fno"),
        "market_context": (f"Market regime {fs['market']['regime']} (confidence {fs['market']['confidence']:.0f})."
                           if fs.get("market") else "Market regime not available."),
        "entry": (f"Preferred ₹{lv.get('entry_low')}–₹{lv.get('entry_high')}; do not chase above ₹{lv.get('no_chase_above')}. "
                  f"{(lv.get('methodology') or {}).get('entry', '')}") if lv else "Not available.",
        "stop": f"₹{lv.get('stop')} ({lv.get('risk_pct')}% risk). {(lv.get('methodology') or {}).get('stop', '')}" if lv else "n/a",
        "targets": (f"T1 ₹{lv.get('target1')}, T2 ₹{lv.get('target2')}, T3 ₹{lv.get('target3')}.") if lv else "n/a",
        "risk_reward": f"Reward:risk to T2 1:{lv.get('rr_t2')}." if lv else "n/a",
        "invalidation": fs.get("invalidation", ""),
        "final_score": f"{sc.get('total', 0):.1f}/100 (earned {sc.get('earned')} of {sc.get('available')} available points).",
        "citations": [{"label": "Engine output", "field": "levels/score"}],
    }


def get_or_build(db: Session, stock: Stock, regenerate: bool = False) -> dict:
    fs = fact_sheet(db, stock)
    if fs.get("status") != "ok":
        return {"status": fs.get("status"), "message": fs.get("message"), "sections": None}
    key = f"ai_cache:{stock.symbol}:{fs['data_as_of']}"
    cached = db.get(AppSetting, key)
    if cached and not regenerate:
        return cached.value
    base = {"generated_at": j(utcnow()), "data_as_of": fs["data_as_of"], "prompt_version": PROMPT_VERSION,
            "deterministic_fallback": deterministic(fs), "fact_sheet": fs,
            "disclaimer": "AI explanation of computed data. Not investment advice; no outcome is certain."}
    if not ai_configured():
        out = base | {"status": "ai_not_configured", "model": None, "sections": base["deterministic_fallback"],
                      "guardrail_flags": [], "message": "Set ANTHROPIC_API_KEY to enable AI explanations."}
        return out
    try:
        data, model = structured_call(SYSTEM, "FACT SHEET (JSON):\n" + json.dumps(fs, default=str), SCHEMA)
        allowed = numbers_in(fs)
        sections, flags = check_obj({k: v for k, v in data.items() if k != "citations"}, allowed)
        sections["citations"] = data.get("citations", [])
        status = "ok" if len([f for f in flags if f.startswith("unverified")]) <= 2 else "ok_with_flags"
        out = base | {"status": status, "model": model, "sections": sections, "guardrail_flags": flags}
    except AIUnavailable as e:
        out = base | {"status": "error", "model": get_settings().ai_model, "sections": base["deterministic_fallback"],
                      "guardrail_flags": [], "message": str(e)}
        return out
    if cached:
        cached.value, cached.updated_at = out, utcnow()
    else:
        db.add(AppSetting(key=key, value=out, updated_at=utcnow()))
    db.commit()
    return out
