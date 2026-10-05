# Security

NIVARA is designed to be self-hosted for one person or a small trusted group. It stores portfolio and tax data
and talks to NSE, optional broker data APIs and the optional Anthropic API. It never places orders.

## Authentication

`app/core/security.py`, `app/api/routes/auth.py`, `app/api/deps.py`.

| Control | Implementation |
|---|---|
| Password hashing | argon2id (`argon2-cffi` `PasswordHasher` defaults) |
| Password policy | ≥ 10 characters, mixed case, at least one digit (registration, admin-created users, password change, CLI) |
| Registration | `POST /api/auth/register` works only while the `users` table is empty; that first user is `admin`. Afterwards accounts are created by an admin or the CLI |
| Login throttling | 10 attempts/minute per client IP and per email (application), plus nginx `limit_req` 10 r/m with burst 5 on `/api/auth/login` |
| Failed logins | Generic "Invalid email or password"; audited as `auth.login_failed` with the email and IP |
| Deactivation | `POST /api/admin/users/{uid}/deactivate`; inactive users are rejected on every request |

## Sessions

- On login/registration a random session id (`secrets.token_urlsafe(32)`) is stored in `user_sessions` with
  expiry, IP and user agent.
- The client receives a JWT (HS256, signed with `SECRET_KEY`) containing the session id, user id, `iat` and `exp`
  (default TTL 12 hours, `SESSION_TTL_MINUTES`).
- Every request verifies the JWT **and** that the server-side session exists, is not revoked and not expired, so
  tokens can be revoked. Logout revokes the session; a password change revokes all other sessions.
- Cookie `nivara_session`: `HttpOnly`, `SameSite=Lax`, `Secure` when `COOKIE_SECURE=true` (set by the production
  compose override), path `/`.
- The same token is returned as `access_token` and can be sent as `Authorization: Bearer ...` (used by scripts).

## CSRF

Double-submit with a session-bound value. The readable cookie `nivara_csrf` holds
`HMAC-SHA256(SECRET_KEY, "csrf:" + session_id)`. For cookie-authenticated `POST`/`PUT`/`PATCH`/`DELETE`
requests the header `x-csrf-token` must equal the cookie and the expected HMAC (constant-time comparisons).
Bearer-token requests are not subject to CSRF checks (browsers do not attach them automatically). The frontend
(`src/lib/api.ts`) sends the header on every non-GET request.

## Authorization

- `get_current_user` on all non-public routes; `require_admin` on `/api/admin/*`, `POST /api/opportunities/run`
  and `PUT /api/settings/{key}`.
- Public routes: `/api/health`, `/api/auth/status`, `/api/auth/register` (first run only), `/api/auth/login`,
  `/api/meta/disclaimers`, `/api/docs`, `/api/openapi.json`.
- User-owned objects (portfolios, transactions, positions, trades, watchlists, alerts, alert events, paper orders,
  backtests, tax profile) are filtered by owner; other users' objects return 404.
- Market data, recommendations, news and settings (read) are shared across users.

## Rate limiting

`app/core/ratelimit.py`: fixed one-minute windows in Redis (`rl:<key>:<bucket>`), falling back to in-process
counters when Redis is unreachable (per process, so limits multiply with uvicorn workers).

| Scope | Limit |
|---|---|
| All `/api/*` except `/api/health` (app) | `RATE_LIMIT_PER_MINUTE` = 240 per client IP → 429 with `Retry-After: 60` |
| Login (app) | `LOGIN_RATE_LIMIT_PER_MINUTE` = 10 per IP and per email |
| nginx `/api/` | 20 r/s per remote address, burst 40 |
| nginx `/api/auth/login` | 10 r/m per remote address, burst 5 |

The client IP is the connection's peer address (`request.client.host`); client-supplied headers are not read
directly. Behind the bundled nginx, `proxy_params_nivara` **overwrites** `X-Forwarded-For` with `$remote_addr`
and uvicorn (`--proxy-headers`) derives the peer from it, so clients cannot inject an address into rate limits or
audit logs. In production the backend port is not published, so requests can only arrive through nginx.

## HTTP hardening

| Header / setting | Where |
|---|---|
| `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` | Backend middleware (all responses) and nginx |
| `Cache-Control: no-store` | Backend, all `/api` responses |
| `Permissions-Policy: camera=(), microphone=(), geolocation=()`, `server_tokens off`, `client_max_body_size 5m` | nginx |
| `Content-Security-Policy` | nginx: `default-src 'self'`; scripts and styles `'self' 'unsafe-inline'`; images `'self' data: blob:`; fonts `'self' data:`; `connect-src 'self'`; `frame-ancestors 'none'`; `base-uri 'self'`; `form-action 'self'` |
| `Strict-Transport-Security` | nginx, commented out until HTTPS is configured |
| `x-request-id` | Backend, every response (also accepted from the client) |
| CORS | `ALLOWED_ORIGINS` only, credentials allowed, methods GET/POST/PUT/PATCH/DELETE, headers `content-type`, `x-csrf-token`, `authorization` |
| `X-Powered-By` | Disabled in Next.js (`poweredByHeader: false`) |

Unhandled exceptions are logged with a stack trace and return a generic 500 body containing only the request id.
The CSP is set by nginx only; requests that reach the backend or the Next.js server directly (development) do not
carry it.

## Secrets

- All secrets come from environment variables / `.env` (`.env` and `.env.*` are git-ignored; `backend/.env` is
  excluded from the Docker build context).
- With `ENVIRONMENT=production` the app refuses to start unless `SECRET_KEY` is at least 32 characters and not the
  development default. Outside production an empty `SECRET_KEY` falls back to the development default.
- Broker tokens and the Anthropic key are read from settings only. The broker adapters state that tokens are never
  logged; `/api/admin/data-sources` reports only whether the required variables are set (`configured`) and never
  returns values.
- `app/core/logging.py::redact` masks values whose key contains `password`, `token`, `secret`, `authorization`,
  `api_key` or `cookie`; it is applied to audit-log data. Request logs record method, path, status and duration
  (not bodies).
- `encrypt_secret` / `decrypt_secret` (Fernet, key from `ENCRYPTION_KEY` or derived from `SECRET_KEY`) and the
  `data_sources.encrypted_secret` column exist but are not used by any current code path (`ENCRYPTION_KEY` is
  documented as optional/reserved); credentials are not stored in the database.

## Audit log

`audit_logs` rows (`app/core/audit.py`) are written for: `user.register`, `auth.login`, `auth.login_failed`,
`auth.logout`, `auth.password_changed`, `user.create`, `user.deactivate`, `portfolio.create`, `portfolio.delete`,
`transaction.add`, `transaction.delete`, `scan.manual`, `settings.update`, `data_source.update`, `job.trigger`.
Admins read them via `GET /api/admin/audit-logs`.

## Input validation

Request bodies are Pydantic models with length limits, regex-constrained enums (sides, segments, exchanges, order
types, regimes), positive/bounded numbers, trade dates not in the future and backtest end after start. SQL is built
with SQLAlchemy expressions; the only raw SQL interpolates fixed table names in the admin health endpoint.

## Containers and network

- Backend runs as uid 10001, frontend as `nextjs` (uid 1001).
- In production only nginx publishes a port (80; 443 once TLS is configured); Postgres, Redis, backend and frontend
  are internal to the compose network. Redis has no password (relies on network isolation).
- The development compose file publishes Postgres (5442), Redis (6381), backend (8000) and frontend (3000) on all
  host interfaces.

## External data flows

| Destination | Data sent |
|---|---|
| NSE (archives, website API, niftyindices.com) | Public GET requests only |
| Upstox / Kite (optional) | Access token and the symbols/instrument keys being quoted |
| Anthropic (optional) | Stock fact sheet (prices, indicators, levels, scores, fundamentals, headlines, F&O and regime data) or one news item's text. No portfolio, tax or user data |
| SMTP / webhook (optional) | Alert title, message and data, to the user's email or `ALERT_WEBHOOK_URL` |
| Sentry (optional) | Error events, 5% trace sampling |

Any signed-in user can trigger AI requests with `POST /api/stocks/{symbol}/analysis` or
`POST /api/news/{nid}/analyze`, which incur API cost. `GET /api/stocks/{symbol}/analysis` never calls the model; it
returns the cached explanation (per stock and data date) or the deterministic one.

## Regulatory scope

The application does not implement order placement. `GET /api/meta/disclaimers` states: "Personal research tool.
Offering personalised recommendations to others may require SEBI registration (Investment Adviser / Research
Analyst). Automated order placement is not implemented."

## Known gaps

- No account lockout beyond rate limiting; no MFA.
- HSTS and TLS must be configured by the operator; the CSP allows `'unsafe-inline'` scripts and styles.
- The in-process rate-limit fallback (when Redis is unreachable) is per worker process.
- Without the bundled nginx (e.g. another proxy), make sure the proxy replaces `X-Forwarded-For` rather than
  appending to it, because uvicorn runs with `--forwarded-allow-ips '*'` in production.
- Any signed-in user can incur AI API cost through the `POST` analysis endpoints.
