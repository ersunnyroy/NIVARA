"""Celery app + beat schedule (IST). Workers run the pipeline stages and heavier jobs (backtests, AI)."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config.settings import get_settings
from app.core.logging import configure_logging

s = get_settings()
configure_logging(s.log_level, s.log_json)
celery = Celery("nivara", broker=s.broker_url, backend=s.result_backend, include=["app.workers.tasks"])
celery.conf.update(
    timezone="Asia/Kolkata",
    enable_utc=False,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=60 * 60 * 3,
    task_soft_time_limit=60 * 60 * 3 - 60,
    beat_schedule={
        "pre-market": {"task": "nivara.pre_market", "schedule": crontab(hour=8, minute=15, day_of_week="mon-fri")},
        "intraday": {"task": "nivara.intraday", "schedule": crontab(minute="*/5", hour="9-15", day_of_week="mon-fri")},
        # Official EOD files are published by early evening; retry later in case of delays.
        "post-market": {"task": "nivara.post_market", "schedule": crontab(hour=19, minute=0, day_of_week="mon-fri")},
        "post-market-retry": {"task": "nivara.post_market", "schedule": crontab(hour=21, minute=30, day_of_week="mon-fri")},
        "news": {"task": "nivara.news", "schedule": crontab(minute="*/20")},
        "fundamentals-weekly": {"task": "nivara.fundamentals_refresh", "schedule": crontab(hour=6, minute=0, day_of_week="sat")},
        "securities-weekly": {"task": "nivara.securities", "schedule": crontab(hour=7, minute=0, day_of_week="sat")},
    },
)
app = celery
