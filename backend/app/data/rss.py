"""Generic RSS/Atom news provider (stdlib XML parsing) for configured secondary feeds."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from app.config.settings import get_settings
from app.data.providers.base import DataUnavailable, NewsProvider
from app.data.types import Announcement, DataQuality, Provenance, ProviderResult

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
_NSE_FORMATS = ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y")


def parse_feed_datetime(value: str | None, naive_tz: ZoneInfo = IST) -> datetime | None:
    """Parse RFC 822 / ISO 8601 / NSE ``05-Oct-2026 09:03:37`` dates. Naive values are taken as ``naive_tz``."""
    if not value or not value.strip():
        return None
    s = value.strip()
    dt: datetime | None = None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    if dt is None:
        for fmt in _NSE_FORMATS:
            try:
                dt = datetime.strptime(s, fmt).replace(tzinfo=naive_tz)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    return dt.replace(tzinfo=naive_tz) if dt.tzinfo is None else dt


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(el: ET.Element, *names: str) -> str | None:
    for child in el:
        if _local(child.tag) in names:
            if _local(child.tag) == "link" and child.get("href"):
                return child.get("href")
            text = (child.text or "").strip()
            if text:
                return text
    return None


_TAG_RE = re.compile(r"<[^>]+>")


def parse_feed(
    data: bytes | str, *, source: str | None = None, source_tier: str = "reputable", feed_url: str | None = None
) -> list[Announcement]:
    """Parse an RSS 2.0 or Atom document into announcements. Items without a parseable date are skipped."""
    root = ET.fromstring(data.encode() if isinstance(data, str) else data)
    channel_title = None
    for el in root.iter():
        if _local(el.tag) in ("channel", "feed"):
            channel_title = _child_text(el, "title")
            break
    src = source or channel_title or (urlparse(feed_url).hostname if feed_url else None) or "rss"
    out: list[Announcement] = []
    skipped = 0
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = _child_text(el, "title")
        published = parse_feed_datetime(_child_text(el, "pubDate", "published", "updated", "date"))
        if not title or published is None:
            skipped += 1
            continue
        body = _child_text(el, "description", "summary", "content")
        out.append(
            Announcement(
                headline=_TAG_RE.sub("", title).strip(),
                published_at=published,
                source=src,
                source_tier=source_tier,
                url=_child_text(el, "link", "guid"),
                body=_TAG_RE.sub("", body).strip() if body else None,
                raw={"feed": feed_url} if feed_url else {},
            )
        )
    if skipped:
        logger.info("rss %s: skipped %d items without title/date", src, skipped)
    return out


class RSSNewsProvider(NewsProvider):
    """Secondary news from configured RSS/Atom feeds (``settings.news_rss_feeds``)."""

    name = "rss"

    def __init__(
        self,
        feeds: list[str],
        source_tier: str = "reputable",
        *,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.feeds = list(feeds)
        self.source_tier = source_tier
        self._http = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": get_settings().nse_user_agent}
        )

    def latest(self) -> ProviderResult:
        if not self.feeds:
            raise DataUnavailable("no RSS feeds configured")
        items: list[Announcement] = []
        warnings: list[str] = []
        for url in self.feeds:
            try:
                resp = self._http.get(url)
                resp.raise_for_status()
                items.extend(parse_feed(resp.content, source_tier=self.source_tier, feed_url=url))
            except (httpx.HTTPError, ET.ParseError) as exc:
                logger.warning("rss feed failed %s: %s", url, exc)
                warnings.append(f"feed failed: {url} ({type(exc).__name__})")
        if len(warnings) == len(self.feeds):
            raise DataUnavailable("all RSS feeds failed: " + "; ".join(warnings))
        items.sort(key=lambda a: a.published_at, reverse=True)
        prov = Provenance(
            source="RSS feeds (secondary)",
            retrieved_at=datetime.now(UTC),
            data_timestamp=items[0].published_at if items else None,
            url=self.feeds[0] if len(self.feeds) == 1 else None,
            quality=DataQuality.UNVERIFIED,
        )
        return ProviderResult(items, prov, warnings)
