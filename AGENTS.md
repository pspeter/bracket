# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Bracket

Bracket is an open-source tournament system supporting single elimination, round-robin, and swiss formats. It has a Python/FastAPI backend and a React/Vite/Mantine frontend, backed by PostgreSQL.

## Development Setup

Prerequisites: `uv`, `pnpm`, `postgresql` (or use the nix devShell via `nix develop`).

The nix devShell auto-starts a local Postgres instance and sets `PG_DSN`, `CORS_ORIGINS`, `ENVIRONMENT` env vars. It also provides a `dev` alias.

### Running Everything (dev mode)

```bash
# With nix devShell:
nix develop
dev  # alias for: process-compose up -f process-compose-example.yml

# Without nix:
./run.sh  # starts backend (port 8400) + frontend (port 3000) in parallel
```

### Running Individually

```bash
# Backend (from backend/):
uv run gunicorn -k bracket.uvicorn.RestartableUvicornWorker bracket.app:app --bind localhost:8400 --workers 1 --reload

# Frontend (from frontend/):
pnpm run dev --port 3000

# Docs site (from docs/):
pnpm run dev --port 3001
```

### Manual Browser Testing With Rodney

For Rodney-based manual browser testing, do not rely on the default `localhost`-only setup.
Start the backend and frontend on addresses the browser can reach, and make sure CORS allows the
frontend origin:

```bash
# Backend (from backend/):
CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000 \
ENVIRONMENT=DEVELOPMENT \
uv run gunicorn -k bracket.uvicorn.RestartableUvicornWorker \
  bracket.app:app \
  --bind 0.0.0.0:8400 \
  --workers 1 \
  --reload

# Frontend (from frontend/):
VITE_API_BASE_URL=http://127.0.0.1:8400 pnpm run dev --port 3000 --host 0.0.0.0
```

If you use different ports, update both `CORS_ORIGINS` and `VITE_API_BASE_URL` to match.

To see Rodney's available commands, run:

```bash
nix develop -c uvx rodney --help
```

### Seed Database

```bash
cd backend && uv run ./cli.py create-dev-db
```

### Dev Credentials

- Email: `test@example.org`
- Password: `aeGhoe1ahng2Aezai0Dei6Aih6dieHoo`

## Commands

Use `nix develop --command` for all of these.

### Backend (run from `backend/`)

| Task | Command |
|---|---|
| Run tests | `ENVIRONMENT=CI uv run pytest . -vvv` |
| Run single test | `ENVIRONMENT=CI uv run pytest tests/path/to/test.py::test_name -vvv` |
| Format | `uv run ruff format .` |
| Lint | `uv run ruff check --fix .` |
| Type check (mypy) | `uv run mypy .` |
| Type check (pyrefly) | `uv run pyrefly check` |
| Pylint | `uv run pylint bracket tests cli.py` |
| Dead code | `uv run vulture` |
| Generate OpenAPI | `uv run ./cli.py generate-openapi` |
| Full precommit suite | `./precommit.sh` |

Tests require a running Postgres. CI uses port 5532 with user/db `bracket_ci` (see `ci.env`). The dev shell uses port 5432 with user/db `bracket_dev`. Set `ENVIRONMENT=CI` when running tests locally to use CI config.

### Frontend (run from `frontend/`)

| Task | Command |
|---|---|
| Type check + format | `pnpm test` |
| Type check only | `pnpm run typecheck` |
| Format check | `pnpm run prettier:check` |
| Format fix | `pnpm run prettier:write` |
| Build | `pnpm run build` |
| Regenerate API client | `pnpm run openapi-ts` |

### Database Migrations

Alembic migrations live in `backend/alembic/versions/`. Migrations auto-run on startup unless `auto_run_migrations` is false.

## Architecture

### Backend (`backend/bracket/`)

- **`app.py`** — FastAPI app with lifespan, CORS middleware, router registration
- **`config.py`** — Pydantic settings loaded from env files (`ci.env`, `dev.env`, `prod.env`, `demo.env`), selected by `ENVIRONMENT` env var
- **`schema.py`** — SQLAlchemy table definitions (the source of truth for DB schema)
- **`database.py`** — Database connection via `databases` library (async) + SQLAlchemy engine
- **`routes/`** — FastAPI routers, one per resource. All routers use a shared `config.api_prefix`. Route dependencies in `routes/util.py` handle fetching + 404 validation
- **`sql/`** — Data access layer; raw SQL queries via `databases`. One file per resource, mirroring `routes/`
- **`models/db/`** — Pydantic models for DB rows, request/response bodies. `models/db/util.py` has composite models (e.g., `RoundWithMatches`, `StageItemWithRounds`)
- **`logic/`** — Business logic separated from routes:
  - `planning/` — match scheduling, conflict detection
  - `ranking/` — ELO/swiss/elimination ranking calculation
  - `scheduling/` — bracket building (round-robin, elimination, swiss)
- **`utils/`** — Shared utilities including `id_types.py` (NewType wrappers for IDs), `db.py` (query helpers), `security.py` (JWT/password)
- **`cli.py`** — Click CLI: `generate-openapi`, `create-dev-db`, `register-user`

### Frontend (`frontend/src/`)

- **`main.tsx`** — React Router routes, Mantine theme, i18n setup
- **`services/`** — API layer using Axios + SWR. `adapter.tsx` has the base fetcher and shared hooks. Other files have resource-specific mutation functions
- **`openapi/`** — Auto-generated TypeScript types from backend OpenAPI schema (via `@hey-api/openapi-ts`). Regenerate with `pnpm run openapi-ts`
- **`components/`** — UI components organized by feature (brackets, builder, dashboard, scheduling, etc.)
- **`pages/`** — Route pages. Tournament pages under `pages/tournaments/[id]/`

### Data Model Hierarchy

Club → Tournament → Stage → StageItem (bracket/group) → Round → Match

StageItems have a `StageType` (round-robin, single elimination, swiss). Stages connect via `StageItemInput` which can reference teams directly or results from a previous stage item.

### API Client Codegen

The backend generates `backend/openapi/openapi.json` via `cli.py generate-openapi`. The frontend consumes this to generate TypeScript types in `frontend/src/openapi/` via `pnpm run openapi-ts`. When changing API response shapes, regenerate both.

## Configuration

Backend uses Pydantic settings with environment-specific `.env` files. Key env vars:
- `ENVIRONMENT` — `DEVELOPMENT`, `CI`, `PRODUCTION`, `DEMO`
- `PG_DSN` — PostgreSQL connection string
- `JWT_SECRET` — required in production
- `CORS_ORIGINS` — comma-separated origins
- `SERVE_FRONTEND` / `API_PREFIX` — for combined deployment (Docker)
