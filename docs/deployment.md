# Deployment and operations

## Services

| Service | Image / command | Port (host) |
|---|---|---|
| `db` | `postgres:16-alpine` (or `DB_IMAGE=timescale/timescaledb:latest-pg16`) | `DB_PORT` → 5432 (default 5442) |
| `redis` | `redis:7-alpine` | `REDIS_PORT` → 6379 (default 6381) |
| `backend` | `backend/Dockerfile` (Python 3.12-slim, non-root uid 10001); runs `alembic upgrade head && python -m app.cli seed && uvicorn ...` | 8000 |
| `worker` | `celery -A app.workers.celery_app worker -l info -c 2` | — |
| `beat` | `celery -A app.workers.celery_app beat -l info --schedule /tmp/celerybeat-schedule` | — |
| `frontend` | `frontend/Dockerfile` (Node 22-alpine, Next.js standalone, non-root) | 3000 |
| `nginx` | `nginx:1.27-alpine`, production override only | 80 (443 to be added with TLS) |

`backend`, `worker`, `beat` and `frontend` are in the compose profile `app`; `db` and `redis` start without a
profile. Host ports 5442/6381 were chosen to avoid clashes with other local Postgres/Redis instances.

## Configuration

Settings are read by `app/config/settings.py` from environment variables and from `.env` / `../.env` relative to
the working directory. Copy `.env.example` to `.env` at the repository root.

`SECRET_KEY`: in development an empty value falls back to a built-in development key. With
`ENVIRONMENT=production` the app refuses to start unless `SECRET_KEY` is at least 32 characters and not the
development default (generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`).

`ALLOWED_ORIGINS` and `NEWS_RSS_FEEDS` accept a comma-separated list, a JSON list, or an empty value.

Settings available but not listed in `.env.example`: `SESSION_TTL_MINUTES` (720), `RATE_LIMIT_PER_MINUTE` (240),
`LOGIN_RATE_LIMIT_PER_MINUTE` (10), `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (default `REDIS_URL`),
`NSE_USER_AGENT`, `DEBUG`, `API_PREFIX` (`/api`).

In Docker, `backend`, `worker` and `beat` load the root `.env` through `env_file` (optional), so every setting
passes through; the `x-backend-env` block in `docker-compose.yml` then overrides the values that must point at the
compose network (`DATABASE_URL`, `REDIS_URL`, `DATA_CACHE_DIR`) and supplies defaults. `backend/.env` is excluded
from the image by `.dockerignore`.

## Local development without full Docker

Postgres and Redis in Docker, backend and frontend on the host.

```bash
cp .env.example .env            # SECRET_KEY may stay empty for local development
docker compose up -d db redis

cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli bootstrap --days 420
.venv/bin/uvicorn app.main:app --reload            # http://localhost:8000/api/docs

# optional, for scheduled pipelines (separate terminals)
.venv/bin/celery -A app.workers.celery_app worker -l info -c 2
.venv/bin/celery -A app.workers.celery_app beat -l info

cd ../frontend
npm install
npm run dev                                         # http://localhost:3000
```

The frontend proxies `/api/*` to `BACKEND_URL` (default `http://localhost:8000`). Open
`http://localhost:3000`: while no user exists the login page offers registration, and the first registered user
becomes `admin`. Further users are created by an admin (`POST /api/admin/users`) or with
`python -m app.cli create-admin EMAIL` (password from `NIVARA_ADMIN_PASSWORD` or a prompt).
`python -m app.cli seed` and `bootstrap` also create an admin from `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` if set.

Without Celery, admin-triggered jobs and backtests run as in-process background tasks; nothing runs on a schedule.

## First-run bootstrap

```bash
.venv/bin/python -m app.cli bootstrap --days 420
```

Runs `seed` and creates the `BOOTSTRAP_ADMIN_EMAIL` admin if configured, then, in order and continuing past
failures: `securities`, `holidays`, `backfill` (420 calendar days of EOD bars, delivery data and index closes),
`corporate_actions` (followed by split/bonus factor derivation), `event_calendar`, `flows`, `news`, `fno`,
`fno_snapshots`, `breadth`, `regime`, `fundamentals` (NIFTY 50 members), `scan`, `outcomes`.

- 420 days covers the 210-session index history the regime needs and the 220-session minimum the scanner applies.
- Backfill makes about three NSE requests per session at ≥ 1 s spacing; files for past sessions are cached on disk
  forever under `DATA_CACHE_DIR`, so re-runs are fast.
- F&O data is fetched for the last session only; F&O history and IV percentiles build up from daily runs.
- FII/DII flows are available for the latest day only and accumulate one day per run.
- Holidays before the current year are inferred from missing bhavcopies. Weekend/holiday special sessions (e.g.
  2026-02-01) are discovered automatically during backfill: when a session's published previous closes disagree with our last stored closes for most stocks, the closed days in between are probed for a bhavcopy and any found are ingested and recorded as `market_holidays` rows with `is_special_session = true` (source `inferred`).
- Fundamentals for the wider `nifty500` universe are fetched by the Saturday job or on demand:
  `python -m app.cli job fundamentals universe=nifty500` (or `symbols=RELIANCE,TCS`).

## Named jobs

```bash
.venv/bin/python -m app.cli job <name> [key=value ...]
# e.g.
.venv/bin/python -m app.cli job eod date=2026-10-01
.venv/bin/python -m app.cli job backfill start=2025-04-01 end=2026-10-01
.venv/bin/python -m app.cli job post_market
.venv/bin/python -m app.cli job scan
```

Job names: `seed`, `securities`, `holidays`, `eod`, `backfill`, `fno`, `fno_snapshots`, `flows`, `news`,
`corporate_actions`, `event_calendar`, `fundamentals`, `breadth`, `regime`, `scan`, `outcomes`, `alerts`, `paper`,
`pre_market`, `post_market`, `replay`. The same jobs can be triggered by an admin via `POST /api/admin/jobs/{job}`.

## Scheduled pipelines (Celery beat, IST)

| Schedule | Task |
|---|---|
| Mon–Fri 08:15 | `nivara.pre_market` |
| Mon–Fri every 5 minutes, 09:00–15:55 (skips when the market is closed) | `nivara.intraday` |
| Mon–Fri 19:00, retry 21:30 | `nivara.post_market` |
| Every 20 minutes | `nivara.news` |
| Saturday 06:00 | `nivara.fundamentals_refresh` (nifty500) |
| Saturday 07:00 | `nivara.securities` |

Celery is configured with `timezone="Asia/Kolkata"`, `task_acks_late`, prefetch 1 and a 3-hour hard time limit.
Pipeline steps are listed in [data-sources.md](data-sources.md#refresh-cadence).

## Full Docker (local)

```bash
cp .env.example .env
docker compose --profile app up -d --build
```

The backend container applies migrations and seeds on start. Run the bootstrap once:

```bash
docker compose exec backend python -m app.cli bootstrap --days 420
```

The NSE cache lives in the `datacache` volume and Postgres data in `pgdata`.

## Production

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile app up -d --build
```

The production override:

- removes host ports from `db`, `redis`, `backend` and `frontend`; only `nginx` publishes port 80 (a commented
  note explains adding 443 once certificates are configured);
- sets `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `LOG_JSON=true` on the backend and runs uvicorn with 4
  workers and `--proxy-headers --forwarded-allow-ips '*'`;
- enables Redis AOF persistence and `restart: unless-stopped` everywhere;
- adds `nginx` with `deploy/nginx/nivara.conf` (`/api/` → backend, `/` → frontend). nginx overwrites
  `X-Forwarded-For` with the real remote address (`proxy_params_nivara`), from which uvicorn's `--proxy-headers`
  derives the client IP used for rate limits and audit logs.

Checklist:

1. `.env`: `SECRET_KEY` (≥ 32 random characters; start-up fails otherwise), a strong `POSTGRES_PASSWORD`, and
   `ALLOWED_ORIGINS` set to your HTTPS origin.
2. TLS: `nivara.conf` only has a `listen 80` server. Add a `listen 443 ssl` block with certificates (and mount
   them), publish `443:443` in `docker-compose.prod.yml`, enable the commented HTTP→HTTPS redirect and the
   `Strict-Transport-Security` header — or terminate TLS at a load balancer. `COOKIE_SECURE=true` requires HTTPS
   for the session cookie.
3. The frontend image bakes the `/api` rewrite at build time from the `BACKEND_URL` build argument (default
   `http://backend:8000`).
4. Run the bootstrap once (`docker compose ... exec backend python -m app.cli bootstrap --days 420`).
5. Register the first user immediately after start-up (registration is open until one user exists), or set
   `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` so `seed` (run on every backend start) or `bootstrap`
   creates the admin.

## Migrations

```bash
cd backend && .venv/bin/alembic upgrade head        # host
docker compose exec backend alembic upgrade head    # Docker (also runs automatically on backend start)
```

To use TimescaleDB, set `DB_IMAGE=timescale/timescaledb:latest-pg16` before the first migration; migration
`0002_timescale` converts the price tables to hypertables when the extension is available and is a no-op
otherwise. See [database.md](database.md#migrations).

## Backups

No backup job is included. A logical backup with the bundled Postgres:

```bash
docker compose exec -T db pg_dump -U nivara -d nivara -Fc > nivara-$(date +%F).dump
# restore into an empty database
docker compose exec -T db pg_restore -U nivara -d nivara --clean --if-exists < nivara-2026-10-05.dump
```

Use your `POSTGRES_USER` / `POSTGRES_DB` values. The NSE disk cache (`datacache` volume / `DATA_CACHE_DIR`) can be
rebuilt from NSE and does not need backing up. With TimescaleDB, follow TimescaleDB's guidance for
`pg_dump`/`pg_restore` of hypertables.

## Monitoring

| Signal | Where |
|---|---|
| Liveness | `GET /api/health` → `status` `ok`/`degraded`, database and Redis checks. Used by the backend Docker `HEALTHCHECK`; the frontend image checks `GET /login` |
| Data freshness | `GET /api/market/status` (`data.is_current`, `sessions_behind`) |
| Data sources, workers, DB | `GET /api/admin/system-health` (admin): per-source GREEN/YELLOW/RED/DISABLED vs SLA, Celery worker ping, DB size and row counts, recent ingestion runs |
| Jobs | `GET /api/admin/jobs` (last 7 days, counts by status); `ingestion_runs` table |
| Logs | JSON logs to stdout with `request_id`; each response has an `x-request-id` header |
| Errors | Optional Sentry via `SENTRY_DSN` (`sentry-sdk` is in `requirements.txt`) |
| Audit | `GET /api/admin/audit-logs` |

## Upgrading

1. Pull the new code and read the changes to `backend/alembic/versions/` and `app/tax/defaults.py`.
2. Back up the database.
3. Rebuild and restart: `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile app up -d --build`
   (migrations and seeding run on backend start), or on the host run `alembic upgrade head` then restart uvicorn,
   the worker and beat.
4. Seeding adds new data sources and model versions but does **not** change existing tax rules or charge
   schedules; apply rate changes as new dated rows (see [tax-engine.md](tax-engine.md#keeping-rules-current)).
5. Check `GET /api/health` and `GET /api/admin/system-health`.
