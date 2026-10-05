"""Test fixtures: isolated SQLite database per test + API client. Synthetic bars are test-only."""
from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("REDIS_URL", "redis://localhost:1/0")  # unreachable → in-process rate limiter
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("ANTHROPIC_API_KEY", "")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core import db as dbmod
from app.models import Base


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    dbmod.set_engine(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    from app.services.reference import seed_reference

    s = dbmod.SessionLocal()
    seed_reference(s)
    yield s
    s.close()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.core.ratelimit import limiter
    from app.main import app

    limiter.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(client):
    r = client.post("/api/auth/register", json={"email": "admin@example.com", "password": "Sup3rSecretPw",
                                                "full_name": "Admin"})
    assert r.status_code == 201, r.text
    client.headers["x-csrf-token"] = r.json()["csrf_token"]
    return client
