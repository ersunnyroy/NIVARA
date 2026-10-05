"""AI news analysis: FACT / INTERPRETATION / SPECULATION kept separate, grounded in the source text."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.client import AIUnavailable, structured_call
from app.ai.guardrails import check_obj, numbers_in
from app.config.settings import get_settings
from app.core.timeutil import utcnow
from app.models import NewsItem, NewsSentiment

PROMPT_VERSION = "news-v1"
SYSTEM = """Classify and summarise one Indian corporate announcement or news item for an investor.
Rules: FACTS must be directly stated in the source text (quote numbers exactly as given). INTERPRETATION is
what the facts may mean for the business. SPECULATION is clearly-labelled possibility. Never present
speculation as fact; never add information not in the text. Social-media rumours are never facts."""
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "event_type", "sentiment", "facts", "interpretation", "speculation"],
    "properties": {
        "summary": {"type": "string"},
        "event_type": {"type": "string", "enum": [
            "earnings", "order_win", "acquisition", "merger", "demerger", "management_change", "regulatory",
            "litigation", "promoter_transaction", "fundraising", "dividend", "buyback", "bonus", "split",
            "credit_rating", "government_policy", "sector_development", "other"]},
        "sentiment": {"type": "number"},
        "facts": {"type": "array", "items": {"type": "string"}},
        "interpretation": {"type": "array", "items": {"type": "string"}},
        "speculation": {"type": "array", "items": {"type": "string"}},
    },
}


def analyze_news(db: Session, item: NewsItem) -> NewsSentiment:
    source = f"Source: {item.source} ({item.source_tier})\nCompany: {item.company}\nHeadline: {item.headline}\n" \
             f"Body: {item.body or ''}"
    try:
        data, model = structured_call(SYSTEM, source, SCHEMA, max_tokens=2000)
    except AIUnavailable:
        raise
    cleaned, flags = check_obj(data, numbers_in(source))
    ns = NewsSentiment(news_id=item.id, model=model or get_settings().ai_model, prompt_version=PROMPT_VERSION,
                       facts=cleaned["facts"], interpretation=cleaned["interpretation"],
                       speculation=cleaned["speculation"], summary=cleaned["summary"],
                       sentiment=max(-1.0, min(1.0, float(data["sentiment"]))), event_type=data["event_type"],
                       guardrail_flags=flags, created_at=utcnow())
    db.add(ns)
    db.commit()
    return ns
