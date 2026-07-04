---
name: verify
description: Build, launch, and drive Bracket end-to-end (backend + frontend + headless Chrome via Rodney) to verify a change at its real surface.
---

# Verify Bracket end-to-end

Recipe that worked in a fresh container (no nix devShell needed):

## Database

Postgres cluster on port 5532 with user/db `bracket_ci` matches `backend/ci.env`:

```bash
sudo sed -i 's/^port = .*/port = 5532/' /etc/postgresql/16/main/postgresql.conf
sudo pg_ctlcluster 16 main start
sudo -u postgres psql -p 5532 -c "CREATE USER bracket_ci WITH PASSWORD 'bracket_ci' SUPERUSER;" \
  -c "CREATE DATABASE bracket_ci OWNER bracket_ci;"
cd backend && ENVIRONMENT=CI uv run ./cli.py create-dev-db
```

## Servers

```bash
# Backend (from backend/) — ci.env has CORS_ORIGINS='*'
ENVIRONMENT=CI uv run gunicorn -k bracket.uvicorn.RestartableUvicornWorker \
  bracket.app:app --bind 0.0.0.0:8400 --workers 1

# Frontend (from frontend/)
pnpm install
VITE_API_BASE_URL=http://127.0.0.1:8400 pnpm run dev --port 3000 --host 0.0.0.0
```

## Login gotcha

The seeded login is the **dummy user**: `admin@example.com` / `adminadmin`
(from `DUMMY_USER` in `bracket/utils/dummy_records.py`). The `ADMIN_PASSWORD`
in `ci.env` does NOT work; neither do the docs' dev credentials.

API token for curl probes:

```bash
curl -s -X POST http://127.0.0.1:8400/token \
  -d "username=admin@example.com&password=adminadmin" \
  -H "Content-Type: application/x-www-form-urlencoded"
```

## Browser (Rodney)

```bash
export PATH=/opt/pw-browsers:$PATH   # pre-installed Chromium
uvx rodney start
uvx rodney open "http://127.0.0.1:3000/login"
uvx rodney input 'input[data-path="email"]' 'admin@example.com'
uvx rodney input 'input[data-path="password"]' 'adminadmin'
uvx rodney click 'button[type="submit"]'
```

## Flows worth driving

- **Organizer match modal**: `/tournaments/1/schedule` (Planning) → click a
  match in the Unscheduled tray → "Details" button opens the Edit Match modal.
  Mantine SegmentedControl/portal elements need `rodney js` click fallbacks
  (find button by textContent). The confirm dialog stacks a second
  `.mantine-Modal-content` — target the **last** one.
- Setting React-controlled inputs needs the native value setter +
  `input` event (plain `.value=` is ignored by Mantine forms).
- Make a ranking best-of-3 to see multi-set UI:
  `PUT /tournaments/1/rankings/{id}?force=true` with
  `{"scoring_type":"MATCH_POINTS","num_sets":3}`.
- Verify persistence directly:
  `sudo -u postgres psql -p 5532 -d bracket_ci -c "SELECT ... FROM matches/match_sets"`.
