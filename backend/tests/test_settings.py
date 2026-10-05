import pytest

from app.config.settings import Settings, get_settings


def test_csv_and_empty_list_settings(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("NEWS_RSS_FEEDS", "")
    s = Settings()
    assert s.allowed_origins == ["http://a.test", "http://b.test"] and s.news_rss_feeds == []
    monkeypatch.setenv("NEWS_RSS_FEEDS", '["https://x.test/rss"]')
    assert Settings().news_rss_feeds == ["https://x.test/rss"]


def test_production_requires_strong_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        get_settings()
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    get_settings.cache_clear()
    assert get_settings().is_production
    get_settings.cache_clear()
