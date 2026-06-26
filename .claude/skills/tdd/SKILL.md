---
name: tdd
description: Implement a GitHub issue or feature using red/green TDD (one failing test at a time). Fetches the issue from GitHub if an issue number is given, then drives the implementation through the test cycle. Use when the user says "tdd", "implement with TDD", or "/tdd <issue>".
---

Implement the following issue. If it references an issue number, fetch and read it from GitHub: $1

Implement using red/green TDD, one failing unit test at a time. If your changes touch the frontend, verify your changes using rodney and show relevant screenshots to the user.

## Workflow

1. Read and understand the issue (fetch from GitHub if a number was given — use `mcp__github__issue_read` with repo `pspeter/bracket`).
2. Plan which layer(s) are affected: backend logic, backend API routes, frontend logic, frontend UI.
3. For each increment of behaviour:
   a. Write ONE failing test. Run it — confirm it fails for the right reason.
   b. Write the minimum production code to make it pass.
   c. Run the test again — confirm it passes.
   d. Commit the green increment.
4. Repeat step 3 until the issue is fully implemented.
5. Run the full test suite for each affected layer to catch regressions.
6. If the frontend was touched, launch the app with rodney and capture screenshots of the affected UI.

## Setting Up the Test Environment

### PostgreSQL (required for backend integration tests)

The CI env file (`backend/ci.env`) targets port 5532, but in this remote environment PostgreSQL runs on port **5432**. Before running integration tests:

```bash
# 1. Start PostgreSQL if not already running
pg_ctlcluster 16 main start

# 2. Create the CI role and database (safe to run multiple times)
sudo -u postgres psql -c "CREATE USER bracket_ci WITH PASSWORD 'bracket_ci';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE bracket_ci OWNER bracket_ci;" 2>/dev/null || true
```

### Backend Tests

Run from `backend/`. Override `PG_DSN` to hit port 5432 instead of 5532:

```bash
# All tests
PG_DSN='postgresql://bracket_ci:bracket_ci@localhost:5432/bracket_ci' \
  ENVIRONMENT=CI uv run pytest . -vvv

# Single test
PG_DSN='postgresql://bracket_ci:bracket_ci@localhost:5432/bracket_ci' \
  ENVIRONMENT=CI uv run pytest tests/path/to/test_file.py::test_function_name -vvv
```

Unit tests (in `tests/unit_tests/`) do not require a database connection. Integration tests (in `tests/integration_tests/`) require Postgres to be running and the `bracket_ci` role/database to exist.

### Frontend Tests

Run from `frontend/`. Install dependencies first if `node_modules` is missing:

```bash
pnpm install       # only needed once per session
pnpm run test:unit # vitest — fast, no browser required
```

`pnpm test` additionally runs `tsc` (type-check) and `prettier:write`. Use `test:unit` during TDD for a tight feedback loop.

Frontend test files live at `src/**/*.test.{ts,tsx}` and use **vitest** with a Node environment — no DOM setup is needed for pure logic tests. Import from `vitest` directly: `import { describe, expect, it } from 'vitest'`.

### Rodney (frontend verification)

After any frontend change, verify behaviour in the browser:

```bash
# Start backend (in one terminal)
CORS_ORIGINS=http://127.0.0.1:3000 ENVIRONMENT=DEVELOPMENT \
  uv run gunicorn -k bracket.uvicorn.RestartableUvicornWorker \
  bracket.app:app --bind 0.0.0.0:8400 --workers 1 --reload

# Start frontend (in another terminal)
VITE_API_BASE_URL=http://127.0.0.1:8400 \
  pnpm run dev --port 3000 --host 0.0.0.0

# First, discover available rodney commands
nix develop -c uvx rodney --help

# Then drive the browser and capture screenshots
nix develop -c uvx rodney screenshot
nix develop -c uvx rodney click "..."
```

Show the relevant screenshots to the user after each rodney verification step.

## Commit Convention

Commit each red→green cycle separately with a concise message. Prefix with `test:` for the failing test commit and no prefix (or `feat:`/`fix:`) for the implementation commit. Push to the current feature branch when done.
