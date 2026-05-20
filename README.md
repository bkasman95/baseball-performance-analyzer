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
| 2 | Analysis engine: anomalies, attribution, NL report | not started |
| 3 | API: full REST surface | not started |
| 4 | Frontend: search, dashboard, drill-down, charts | not started |
| 5 | Auth + deploy + scheduled refresh | not started |
| 6 | Polish | not started |

---

## Quick start (local)

Requires Docker and Docker Compose.

```bash
cp .env.example .env
# Edit .env: set ADMIN_PASSWORD and JWT_SECRET at minimum.
docker compose up --build
```

When everything is up:

- API:      http://localhost:8000  (docs at `/docs`, health at `/api/health`)
- Web:      http://localhost:5173
- Postgres: localhost:5432  (creds from `.env`)

The first start downloads the Python ML wheels — give it a few minutes.

### Running tests

```bash
docker compose exec api pytest -q
```

Tests use an isolated SQLite DB and tmp cache dir; they don't hit the network.

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

1. Push the repo to GitHub.
2. In Render: **New +** → **Blueprint** → pick this repo.
3. Render reads `render.yaml`. Set the following secrets in the dashboard
   when prompted:
   - `ADMIN_EMAIL` (e.g. `bkasman95@gmail.com`)
   - `ADMIN_PASSWORD` (pick a strong one)
   - `CORS_ORIGINS` — once the web service has a URL, set this to it
     (e.g. `https://diamondscope-web.onrender.com`).
   - `VITE_API_BASE_URL` — set to the API URL
     (e.g. `https://diamondscope-api.onrender.com`).
4. After the first deploy, redeploy the web service so it picks up the
   `VITE_API_BASE_URL` build-time variable.

Free-tier caveats:
- Web services sleep after 15 min idle on the free plan — first request
  after sleep is slow.
- Persistent disks require a paid plan (~$1/mo for 1 GB).
- Free Postgres is wiped after 90 days — back up if it matters to you.

---

## Environment variables

See `.env.example` for the canonical list. The important ones:

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins |
| `JWT_SECRET` | Long random string — Render auto-generates one |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seeded on first boot (Phase 5) |
| `CACHE_DIR` | Where Parquet cache lives (persistent volume in prod) |
| `DEFAULT_SEASON_WINDOW` | Default number of seasons to analyze |
| `VITE_API_BASE_URL` | Frontend → API URL (build-time) |
