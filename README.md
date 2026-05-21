# DiamondScope

MLB player performance analyzer. Search a player, get automated anomaly
detection plus probable-cause attribution — year-over-year and within-season —
backed by FanGraphs / Baseball Savant data via `pybaseball`.

> **Honesty note.** Findings are **probable causes / likely drivers**, not
> proven causation. The analysis is correlational, domain-guided. The UI
> labels things accordingly.

---

## Current status

| Phase | Description | Status |
|---|---|---|
| 0 | Scaffolding: Docker Compose, FastAPI, React, Postgres, health endpoint | done |
| 1 | Data layer: pybaseball + Savant wrappers, Parquet cache, retries | done |
| 2 | Analysis engine: anomalies, attribution, NL report | done |
| 3 | API: full REST surface (search, profile, analysis, jobs, timeseries, refresh) | done |
| 4 | Frontend: search, dashboard, drill-down, trend charts | done |
| 5 | Auth (JWT) + admin seed + scheduler + saved analyses + deploy config | done |
| 6 | Polish (loading states, code-splitting, two-way player handling, etc.) | not started |

---

## Quick start (local)

Requires Docker and Docker Compose.

```bash
cp .env.example .env
# Edit .env: set ADMIN_PASSWORD (and JWT_SECRET to something long+random).
docker compose up --build
```

When everything is up:

- API:      http://localhost:8000  (docs at `/docs`, health at `/api/health`)
- Web:      http://localhost:5173
- Postgres: localhost:5432  (creds from `.env`)

On first boot, an admin user is auto-seeded from `ADMIN_EMAIL` /
`ADMIN_PASSWORD`. Sign in at http://localhost:5173/login with those creds.

The first start downloads the Python ML wheels — give it a few minutes.

### Managing users

```bash
# Inside the running api container:
docker compose exec api python -m app.cli create-user --email a@b.c --password 'xxx' --name 'Alice'
docker compose exec api python -m app.cli set-password --email a@b.c --password 'new'
docker compose exec api python -m app.cli list-users
```

### Running tests

```bash
docker compose exec api pytest -q
```

Tests use an isolated SQLite DB and tmp cache dir; they don't hit the
network or pybaseball.

---

## Architecture

```
React SPA (Vite) ───▶ FastAPI ───▶ Postgres (users + cache index)
                          │
                          └────▶ Parquet cache (persistent volume)
                                      ▲
                                      └── pybaseball / Savant
```

- **Data layer** (`backend/app/data/`) — the only module allowed to touch
  `pybaseball` or Baseball Savant. Every fetch goes through `read_through_cache`
  which persists to Parquet and indexes in Postgres.
- **Analysis layer** (`backend/app/analysis/`) — coming in Phase 2.
- **API** (`backend/app/main.py`) — FastAPI, routes under `/api`.
- **Frontend** (`frontend/`) — React + Vite + TypeScript + Tailwind + Recharts.

See `a3165d1c-baseballperformanceanalyzerprojectplan.md` for the full spec.

---

## Repository layout

```
.
├── docker-compose.yml
├── render.yaml                # Render Blueprint
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py            # FastAPI app + /api/health
│   │   ├── config.py          # pydantic-settings
│   │   ├── db.py              # SQLAlchemy engine + Base
│   │   ├── models/            # users, cache_entries
│   │   └── data/              # Phase 1 — players, aggregates, statcast, leaderboards, savant
│   └── tests/
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx
        ├── api/client.ts
        └── pages/             # Health, Search, Login, Dashboard
```

---

## Deploying to Render

This repo includes a `render.yaml` Blueprint that provisions everything in
one shot: Postgres + API (with persistent disk for the cache) + web frontend.

**Step-by-step:**

1. Push this repo to GitHub (already done if you're reading this).
2. Go to https://dashboard.render.com → **New +** → **Blueprint**.
3. Connect your GitHub account and pick `baseball-performance-analyzer`.
4. Render reads `render.yaml` and shows the three services it will create.
   You'll be prompted for these secrets — fill them in:

   | Var | Set on | Value |
   |---|---|---|
   | `ADMIN_EMAIL` | `diamondscope-api` | your email |
   | `ADMIN_PASSWORD` | `diamondscope-api` | a strong password (used once to seed your admin user) |
   | `CORS_ORIGINS` | `diamondscope-api` | leave blank for now — you'll set it after step 6 |
   | `VITE_API_BASE_URL` | `diamondscope-web` | leave blank for now — set after step 6 |

   `JWT_SECRET` is auto-generated. `DATABASE_URL` is wired from the managed
   Postgres instance automatically.

5. Click **Apply** and wait. The API build is slow (~5–10 min) because
   scikit-learn / scipy / shap have to compile.

6. Once both services are live, copy each URL from the Render dashboard
   and fill in the variables you left blank:
   - On `diamondscope-api`: set `CORS_ORIGINS=https://diamondscope-web-XXXX.onrender.com`
   - On `diamondscope-web`: set `VITE_API_BASE_URL=https://diamondscope-api-XXXX.onrender.com`
   - **Manual Deploy → Deploy latest commit** on the web service so the
     new `VITE_API_BASE_URL` is baked into the build.

7. Open the web URL, sign in with the admin email + password you set in step 4.

**Free-tier caveats:**
- Web services sleep after 15 min idle on the free plan — first request
  after sleep is slow (~30 s cold start).
- Persistent disks require a paid plan (~$1/mo for 1 GB) — needed so the
  Parquet cache survives deploys. Without it, every restart re-fetches.
- Free Postgres is wiped after 90 days. Saved analyses and user accounts
  will be lost. Use a $7/mo Starter Postgres if you care about persistence.

**Adding more users in production:**

```bash
# From your laptop, against the deployed API URL:
curl -X POST https://diamondscope-api-XXXX.onrender.com/api/auth/login \
  -d "username=admin@example.com&password=YOUR_ADMIN_PW"
# Then use the token to call any protected endpoint, or shell into the
# Render container and run: python -m app.cli create-user --email ...
```

---

## Environment variables

See `.env.example` for the canonical list. The important ones:

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins |
| `JWT_SECRET` | Long random string — Render auto-generates one |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Auto-seeded on first boot if no users exist |
| `CACHE_DIR` | Where Parquet cache lives (persistent volume in prod) |
| `DEFAULT_SEASON_WINDOW` | Default number of seasons to analyze |
| `VITE_API_BASE_URL` | Frontend → API URL (build-time) |
| `DIAMONDSCOPE_DISABLE_SCHEDULER` | Set to `1` to disable the nightly cache refresh job |
