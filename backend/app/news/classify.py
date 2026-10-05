"""Deterministic (rule-based) event classification and sentiment for announcements/news.

This is the always-available baseline; the optional LLM layer (app/ai) may refine summaries but its
output is stored separately and never overwrites these fields silently.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

CLASSIFIER_VERSION = "rules-v1"

# (event_type, regex, base_sentiment, impact, horizon)
RULES: list[tuple[str, str, float, str, str]] = [
    ("earnings", r"financial results|quarterly results|audited results|unaudited results|outcome of board meeting.*result", 0.0, "high", "short"),
    ("order_win", r"\border(s)?\b.*(win|won|receiv|secur|bag|award)|letter of award|\bLoA\b|purchase order", 0.5, "medium", "medium"),
    ("acquisition", r"acqui(re|sition)|takeover|stake purchase", 0.2, "medium", "long"),
    ("merger", r"\bmerger\b|amalgamation|scheme of arrangement", 0.1, "medium", "long"),
    ("demerger", r"demerger|de-merger", 0.2, "medium", "long"),
    ("management_change", r"resign|appointment|cessation|change in (director|management|kmp)|\bCEO\b|\bCFO\b|managing director", -0.05, "low", "medium"),
    ("regulatory", r"\bSEBI\b|\bRBI\b|show cause|penalt|regulator|warning letter|\bUSFDA\b|observation|inspection|import alert", -0.3, "medium", "medium"),
    ("litigation", r"litigation|court|tribunal|\bNCLT\b|arbitration|lawsuit|\bFIR\b|search and seizure|raid", -0.4, "medium", "medium"),
    ("promoter_transaction", r"promoter.*(sale|sell|pledge|acqui|purchase|creation|invocation)|pledge|encumbrance|SAST|insider trading", 0.0, "medium", "short"),
    ("fundraising", r"\bQIP\b|preferential|rights issue|fund rais|non-convertible|\bNCD\b|commercial paper|allotment of (equity|warrants)", -0.05, "low", "medium"),
    ("dividend", r"dividend", 0.2, "low", "short"),
    ("buyback", r"buy[- ]?back", 0.5, "medium", "short"),
    ("bonus", r"\bbonus\b", 0.3, "medium", "short"),
    ("split", r"sub-division|split", 0.15, "low", "short"),
    ("credit_rating", r"credit rating|rating(s)? (re)?affirm|upgrade|downgrade|\bCRISIL\b|\bICRA\b|\bCARE\b|India Ratings", 0.0, "medium", "medium"),
    ("government_policy", r"government|ministry|policy|\bPLI\b|budget|tariff|duty", 0.0, "medium", "long"),
    ("sector_development", r"sector|industry", 0.0, "low", "long"),
]

POSITIVE = r"upgrade|record|highest|growth|increase|expan|commission|award|won|bag|secure|approval|approved|launch|profit up|beats|robust|strong"
NEGATIVE = r"downgrade|decline|loss|fall|default|delay|fraud|penalt|resign|reject|suspend|shut|fire|strike|lower|weak|impair|withdraw|invocation"


@dataclass(slots=True)
class Classification:
    event_type: str
    sentiment: float
    sentiment_label: str
    impact: str
    horizon: str
    confidence: float
    matched: list[str]


def classify(text: str, source_tier: str = "primary") -> Classification:
    t = text or ""
    event, base, impact, horizon, matched = "other", 0.0, "low", "short", []
    for name, pattern, s, imp, hz in RULES:
        if re.search(pattern, t, re.IGNORECASE):
            event, base, impact, horizon = name, s, imp, hz
            matched.append(name)
            break
    pos = len(re.findall(POSITIVE, t, re.IGNORECASE))
    neg = len(re.findall(NEGATIVE, t, re.IGNORECASE))
    s = base + 0.15 * (pos - neg)
    if event == "credit_rating":
        s += 0.4 if re.search(r"upgrade", t, re.I) else -0.5 if re.search(r"downgrade", t, re.I) else 0.0
    if event == "promoter_transaction":
        s += -0.4 if re.search(r"pledge|sale|sell|invocation", t, re.I) else 0.3 if re.search(r"acqui|purchase", t, re.I) else 0
    s = max(-1.0, min(1.0, s))
    label = "positive" if s >= 0.2 else "negative" if s <= -0.2 else "neutral"
    conf = 0.35 + (0.2 if matched else 0.0) + (0.15 if source_tier == "primary" else 0.0) + min(0.1, 0.03 * (pos + neg))
    if source_tier == "other":
        conf = min(conf, 0.3)
    return Classification(event, round(s, 3), label, impact, horizon, round(min(conf, 0.85), 2), matched)


def dedupe_hash(source: str, headline: str, published_at: datetime, url: str | None) -> str:
    key = f"{source}|{(headline or '').strip().lower()}|{published_at.isoformat()[:16]}|{url or ''}"
    return hashlib.sha256(key.encode()).hexdigest()


IMPACT_W = {"low": 0.5, "medium": 1.0, "high": 1.5}


def news_component(items: list, as_of: datetime, lookback_days: int = 14) -> tuple[float | None, list[str], list[str], str | None]:
    """Aggregate recent items into a 0-100 score (50 = neutral / no news). `items` are NewsItem-like objects
    with published_at, sentiment, impact, headline, event_type, source_tier. Only items published at or
    before `as_of` are used (point-in-time)."""
    recent = [i for i in items if i.published_at <= as_of and i.published_at >= as_of - timedelta(days=lookback_days)]
    if not recent:
        return 50.0, [], [], None
    num, den = 0.0, 0.0
    why, caution = [], []
    for i in recent:
        age = max((as_of - i.published_at).total_seconds() / 86400.0, 0.0)
        tier_w = 1.0 if i.source_tier == "primary" else 0.6 if i.source_tier == "reputable" else 0.2
        w = IMPACT_W.get(i.impact, 0.5) * tier_w * (0.5 ** (age / 7.0))
        num += w * i.sentiment
        den += w
        line = f"{i.published_at:%d %b}: {i.headline[:110]} ({i.event_type.replace('_', ' ')}, {i.source_tier})"
        if i.sentiment >= 0.2:
            why.append(line)
        elif i.sentiment <= -0.2:
            caution.append(line)
    agg = num / den if den else 0.0
    return round(50.0 + 50.0 * max(-1.0, min(1.0, agg)), 2), why[:3], caution[:3], None
