# NIVARA frontend

Next.js web UI for the NIVARA API. All data comes from the backend; the frontend holds no business logic for
scores, levels, charges or tax. See the [repository README](../README.md) and [docs/](../docs/) for the system.

## Stack

| Package | Version | Use |
|---|---|---|
| Next.js (App Router) | 16.3.8 | Routing, standalone production server, `/api` rewrite |
| React / React DOM | 19.2.8 | UI |
| TypeScript | 5 | Types (`src/lib/types.ts` mirrors API payloads) |
| @tanstack/react-query | 5 | Data fetching and caching (30 s stale time, no refetch on focus, no retries on 4xx/503) |
| lightweight-charts | 5 | Candlestick charts (`src/components/charts/CandleChart.tsx`) |
| Tailwind CSS | 4 | Styling (`src/app/globals.css`, light/dark theme) |
| lucide-react, clsx | — | Icons, class names |

This Next.js version has breaking changes from older releases; see `AGENTS.md`.

## Scripts

```bash
npm install
npm run dev      # development server on http://localhost:3000
npm run build    # production build (output: standalone)
npm run start    # serve the production build
npm run lint     # ESLint (eslint-config-next core-web-vitals + typescript)
```

The backend must be running for pages to load data (`uvicorn app.main:app` on port 8000 by default).

## Backend URL and the `/api` rewrite

The browser only talks to the frontend's own origin. `next.config.ts` rewrites `/api/:path*` to
`${BACKEND_URL}/api/:path*` (default `http://localhost:8000`), so the session cookie is first-party and no CORS is
involved.

- `next dev` / `next start` read `BACKEND_URL` when the config loads (at start-up).
- The Docker image uses `output: "standalone"`, where rewrites are fixed **at build time**. Pass the URL as a build
  argument: `docker build --build-arg BACKEND_URL=http://backend:8000 .` (`docker-compose.yml` does this; the
  Dockerfile default is also `http://backend:8000`).

In production the bundled nginx routes `/api/` directly to the backend and everything else to this server.

## Structure

```
src/
├── proxy.ts                 # redirects page requests without a nivara_session cookie to /login?next=...
├── app/
│   ├── layout.tsx           # root layout, theme script, providers
│   ├── providers.tsx        # React Query client
│   ├── page.tsx             # redirects to /dashboard
│   ├── login/               # sign in; first-run admin registration while no user exists
│   └── (app)/               # authenticated pages wrapped in AppShell
│       ├── dashboard, market, opportunities, stocks, stocks/[symbol], news, fno
│       ├── portfolio, portfolio/[id], paper, trades, watchlist, alerts, tax
│       ├── recommendations, performance, backtesting, settings
│       └── <page>/_components/   # page-specific components
├── components/
│   ├── ui/                  # Button, Card, Table, Tabs, Dialog, Num, DataStamp, Disclaimer, States, ...
│   ├── layout/              # AppShell, nav, UserMenu, AlertsBell, MarketStatusPill, ThemeToggle
│   ├── domain/              # opportunities table, recommendation detail, score breakdown, holdings, ...
│   ├── stock/               # stock page header, chart panel, trade setup, panels
│   └── charts/              # candlestick chart, small SVG charts
└── lib/
    ├── api.ts               # fetch wrapper, CSRF header, ApiError, 401 handling
    ├── hooks.ts             # React Query hooks per endpoint (useMe, useLogin, useMarketStatus, ...)
    ├── types.ts             # API response types
    ├── nav.ts               # sidebar groups and mobile primary routes
    ├── format.ts            # INR / number / date formatting
    ├── store.ts             # small localStorage-backed state
    └── theme.ts             # light / dark / system theme
```

## Auth and CSRF on the client

- **Session cookie.** `POST /api/auth/login` (or first-run `POST /api/auth/register`) sets the httpOnly
  `nivara_session` cookie and the readable `nivara_csrf` cookie. Requests use `credentials: "same-origin"`, so the
  cookie is sent automatically through the rewrite. The frontend never stores the token itself.
- **CSRF.** `src/lib/api.ts` reads the `nivara_csrf` cookie and sends it as the `x-csrf-token` header on every
  non-GET request; the backend checks it against the cookie and the session (double submit).
- **Route guard.** `src/proxy.ts` is an optimistic check: page requests without a `nivara_session` cookie are
  redirected to `/login` (with `?next=`). The real check happens on every API call; `AppShell` loads `/api/auth/me`
  and redirects to `/login` if it fails.
- **Expired sessions.** Any 401 from a non-auth endpoint triggers a full navigation to `/login?next=<current page>`,
  dropping cached query data.
- **Logout** calls `POST /api/auth/logout` (which revokes the server-side session and clears both cookies) and
  returns to `/login`.
- **Registration.** The login page calls `/api/auth/status`; while `registration_open` is true it shows "Create
  the first (admin) account" instead of sign-in.

## Data display conventions

Prices and analytics are shown with their data date and source (`DataStamp`); tax and charge figures carry the
backend's `ESTIMATED` label and disclaimers (`Disclaimer`). A 503 or `status: data_unavailable` from the backend is
rendered as an unavailable/empty state, not as zeros.
