"""Command-line entrypoint: `python -m app.cli <command>`.

  seed                         seed reference data (exchanges, sectors, sources, tax rules, charges)
  create-admin EMAIL           create an admin user (password read from NIVARA_ADMIN_PASSWORD or prompt)
  job NAME [k=v ...]           run a named job, e.g. `job backfill start=2025-04-01 end=2026-10-01`
  bootstrap [--days N]         seed + securities + holidays + backfill N days + derived analytics + scan
"""
from __future__ import annotations

import getpass
import json
import os
import sys

from app.config.settings import get_settings
from app.core.db import session_scope
from app.core.logging import configure_logging


def main(argv: list[str]) -> int:
    configure_logging(get_settings().log_level, json_logs=False)
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    from app.services.jobs_runner import run_named_job

    if cmd == "seed":
        with session_scope() as db:
            print(json.dumps(run_named_job(db, "seed", {}), default=str))
            _bootstrap_admin(db)
        return 0
    if cmd == "create-admin":
        email = rest[0]
        pw = os.environ.get("NIVARA_ADMIN_PASSWORD") or getpass.getpass("Password: ")
        with session_scope() as db:
            _create_admin(db, email, pw)
        return 0
    if cmd == "job":
        params = dict(kv.split("=", 1) for kv in rest[1:])
        if "symbols" in params:
            params["symbols"] = params["symbols"].split(",")
        with session_scope() as db:
            print(json.dumps(run_named_job(db, rest[0], params), default=str, indent=1))
        return 0
    if cmd == "bootstrap":
        days = int(rest[rest.index("--days") + 1]) if "--days" in rest else 420
        with session_scope() as db:
            for job, params in (("seed", {}), ("securities", {}), ("holidays", {}), ("backfill", {"days": days}),
                                ("corporate_actions", {}), ("event_calendar", {}), ("flows", {}), ("news", {}),
                                ("fno", {}), ("fno_snapshots", {}), ("breadth", {}), ("regime", {}),
                                ("fundamentals", {"universe": "nifty50"}), ("scan", {"trigger": "bootstrap"}),
                                ("outcomes", {})):
                try:
                    res = run_named_job(db, job, params)
                    print(f"[{job}] {json.dumps(res, default=str)[:400]}")
                except Exception as e:
                    db.rollback()
                    print(f"[{job}] FAILED: {type(e).__name__}: {e}")
        return 0
    print(__doc__)
    return 1


def _bootstrap_admin(db) -> None:
    s = get_settings()
    if s.bootstrap_admin_email and s.bootstrap_admin_password:
        _create_admin(db, s.bootstrap_admin_email, s.bootstrap_admin_password, quiet_if_exists=True)


def _create_admin(db, email: str, password: str, quiet_if_exists: bool = False) -> None:
    from email_validator import EmailNotValidError, validate_email
    from sqlalchemy import select

    from app.core.security import hash_password, password_problems
    from app.models import User

    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError as e:
        raise SystemExit(f"Invalid email: {e}") from e
    if db.scalar(select(User).where(User.email == email.lower())):
        if not quiet_if_exists:
            print("User already exists")
        return
    probs = password_problems(password)
    if probs:
        raise SystemExit("Password needs " + ", ".join(probs))
    db.add(User(email=email.lower(), password_hash=hash_password(password), role="admin", full_name="Admin"))
    print(f"Admin {email} created")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
