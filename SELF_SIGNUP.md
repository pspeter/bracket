# Self-Signup Feature — Implementation Guide

Players can sign themselves up for a tournament by following a public link containing a random token. No login required.

## Overview

Tournament admins enable self-signup in tournament settings. This generates a unique token-based URL. Visitors to that URL see a form where they can enter their name and either join an existing team, create a new team, or sign up without a team (to be manually assigned later by the admin). After submitting, they see a brief success message and are redirected to the public dashboard.

## Data Model Changes

### New columns on `tournaments` table

Add to `backend/bracket/schema.py` in the `tournaments` table:


| Column           | Type      | Nullable   | Default | Purpose                         |
| ---------------- | --------- | ---------- | ------- | ------------------------------- |
| `signup_enabled` | `Boolean` | `NOT NULL` | `false` | Toggle for self-signup          |
| `signup_token`   | `String`  | `NULL`     | `NULL`  | Random token for the signup URL |
| `max_team_size`  | `Integer` | `NOT NULL` | `4`     | Max players allowed per team    |


The `signup_token` is generated once when signup is first enabled. It should be a `secrets.token_urlsafe(32)` value. It is stored on the tournament and never changes (no regeneration/revocation needed).

### Alembic migration

Create a new migration in `backend/alembic/versions/`. Follow the pattern of existing migrations like `85d260b43ad4_create_tournaments_dashboard_endpoint.py`:

```python
def upgrade() -> None:
    op.add_column("tournaments", sa.Column("signup_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("tournaments", sa.Column("signup_token", sa.String(), nullable=True))
    op.add_column("tournaments", sa.Column("max_team_size", sa.Integer(), nullable=False, server_default="4"))

def downgrade() -> None:
    op.drop_column("tournaments", "signup_enabled")
    op.drop_column("tournaments", "signup_token")
    op.drop_column("tournaments", "max_team_size")
```

### Model changes

`**backend/bracket/models/db/tournament.py**` — add to `TournamentInsertable`:

```python
signup_enabled: bool = False
signup_token: str | None = None
max_team_size: int = Field(4, ge=1)
```

Add the same fields to `TournamentUpdateBody` (except `signup_token`, which is managed automatically, not set by the user directly through the update body).

## Backend API Changes

### New auth dependency

In `backend/bracket/routes/auth.py`, add a dependency that validates the signup token:

```python
async def tournament_by_signup_token(signup_token: str) -> Tournament:
    """Fetch tournament by signup token. Raises 404 if not found or signup disabled."""
```

This should:

1. Query the `tournaments` table for a row matching `signup_token` and `signup_enabled=True` and `status='OPEN'`
2. Raise `404` if not found, disabled, or archived
3. Return the `Tournament` object

### New route file: `backend/bracket/routes/signup.py`

Create a new route file with `router = APIRouter(prefix=config.api_prefix)`.

Register it in `backend/bracket/app.py` by adding `from bracket.routes import ... signup` to the imports and `"Signup": signup.router` to the `routers` dict.

#### `GET /signup/{signup_token}` — Get tournament info for signup page

Returns tournament name, teams (with player counts), and `max_team_size` so the frontend can render the signup form. This endpoint is **public** (no auth).

Response model — create a dedicated response type:

```python
class SignupTeamInfo(BaseModel):
    id: TeamId
    name: str
    player_count: int
    is_full: bool  # player_count >= tournament.max_team_size

class SignupTournamentInfo(BaseModel):
    tournament_id: TournamentId
    tournament_name: str
    teams: list[SignupTeamInfo]
    max_team_size: int
    dashboard_endpoint: str | None  # for redirect after signup

class SignupInfoResponse(DataResponse[SignupTournamentInfo]):
    pass
```

Implementation:

1. Use `tournament_by_signup_token` dependency to get the tournament
2. Fetch teams with player counts for this tournament
3. Return the info (only expose what's needed — no scores, no ELO, etc.)

#### `POST /signup/{signup_token}` — Submit signup

Request body:

```python
class SignupBody(BaseModelORM):
    player_name: str = Field(..., min_length=1, max_length=30)
    team_action: Literal["join", "create", "none"]
    team_id: TeamId | None = None      # required when team_action == "join"
    team_name: str | None = None       # required when team_action == "create", max_length=30
```

Implementation:

1. Use `tournament_by_signup_token` dependency
2. **Validate player name is unique** within the tournament — query existing players and check `player_name` doesn't already exist (case-insensitive). Return `400` with a clear message if duplicate.
3. **Check subscription limits** — count existing players (and teams if creating). If at capacity, return `400` with "tournament is full" message. Since there's no authenticated user to check subscription against, look up the tournament's club owner and use their subscription tier for limit checks.
4. Create the player via `insert_player()` (using `PlayerBody(name=player_name, active=True)`).
5. Based on `team_action`:
  - `"join"`: Validate `team_id` is not None, belongs to this tournament, and the team is not full (`player_count < max_team_size`). Insert into `players_x_teams`.
  - `"create"`: Validate `team_name` is not None. Create a new team via `teams.insert()`. Insert into `players_x_teams`.
  - `"none"`: Do nothing — the player exists in the tournament without a team (they appear in the unassigned player pool for the admin to assign manually).
6. Return `SuccessResponse`

### Tournament settings changes

`**backend/bracket/routes/tournaments.py`** — in the `update_tournament` endpoint:

When `signup_enabled` is being set to `True` and the tournament doesn't already have a `signup_token`, generate one:

```python
import secrets
if tournament_body.signup_enabled and not existing_tournament.signup_token:
    # Generate token on first enable
    signup_token = secrets.token_urlsafe(32)
    # Include in the update values
```

The token persists even if signup is toggled off and back on.

### SQL layer

`**backend/bracket/sql/signup.py**` — create a new file with:

```python
async def get_tournament_by_signup_token(signup_token: str) -> Tournament | None:
    """Fetch tournament where signup_token matches and signup is enabled."""

async def get_signup_team_info(tournament_id: TournamentId) -> list[SignupTeamInfo]:
    """Fetch teams with their player counts for the signup page."""

async def check_player_name_exists(tournament_id: TournamentId, name: str) -> bool:
    """Case-insensitive check for duplicate player name in tournament."""
```

For `get_signup_team_info`, query teams joined with a count from `players_x_teams`:

```sql
SELECT t.id, t.name, COUNT(pxt.player_id) as player_count
FROM teams t
LEFT JOIN players_x_teams pxt ON pxt.team_id = t.id
WHERE t.tournament_id = :tournament_id AND t.active = true
GROUP BY t.id, t.name
ORDER BY t.name
```

For `check_player_name_exists`:

```sql
SELECT COUNT(*) FROM players
WHERE tournament_id = :tournament_id AND LOWER(name) = LOWER(:name)
```

## Frontend Changes

### New standalone page: `frontend/src/pages/signup.tsx`

This is a **public** page at route `/signup/:signup_token`. It does **not** use `TournamentLayout` (no sidebar, no auth check). It should use the same Mantine theme/provider that wraps the app.

#### Route registration

In `frontend/src/main.tsx`, add:

```tsx
import SignupPage from './pages/signup';

// Inside <Routes>:
<Route path="/signup/:signup_token" element={<SignupPage />} />
```

Place this alongside the other public routes (near `/login`, `/create-account`).

#### Page structure

The page has three states:

**1. Loading state** — Show a skeleton/spinner while fetching tournament info.

**2. Form state** — Show:

- Tournament name as a title
- A brief description of the signup process (2-3 sentences)
- Text input for player name (required, max 30 chars)
- Radio group for team action with three options:
  - **"Join an existing team"** — reveals a Select dropdown of teams that are not full. Each option shows `"TeamName (3/4 players)"`. Teams that are full (`is_full: true`) should not appear in the dropdown.
  - **"Create a new team"** — reveals a text input for team name (required, max 30 chars)
  - **"No team (assign me later)"** — no additional input
- Submit button

**3. Success state** — Show a success message ("You have been registered!") for 2 seconds, then redirect to `/tournaments/{dashboard_endpoint}/dashboard`. If `dashboard_endpoint` is null, just show the success message without redirect.

#### Error handling

- If the `GET /signup/{token}` returns 404, show a "Signup link is invalid or signup is closed" message.
- If the `POST` returns 400 with "tournament is full", show a "Tournament is full" error.
- If the `POST` returns 400 with duplicate name, show "A player with this name already exists".
- Use Mantine `notifications` for errors (same pattern as the rest of the app).

### New API service: `frontend/src/services/signup.tsx`

This service must **not** use the authenticated axios instance from `adapter.tsx`. Create a plain axios instance without the `Authorization` header:

```tsx
import axios from 'axios';
import { getBaseApiUrl } from './adapter';

const signupAxios = axios.create({ baseURL: getBaseApiUrl() });

export async function getSignupInfo(signup_token: string) {
    return signupAxios.get(`/signup/${signup_token}`);
}

export async function submitSignup(signup_token: string, body: SignupBody) {
    return signupAxios.post(`/signup/${signup_token}`, body);
}
```

### Tournament settings page changes

`**frontend/src/pages/tournaments/[id]/settings.tsx**` — in the `GeneralTournamentForm`:

Add a new `Fieldset` (e.g. legend: "Self-Signup") containing:

1. A `NumberInput` for `max_team_size` (min 1)
2. A `Checkbox` for `signup_enabled` ("Allow players to sign up for this tournament via a public link")
3. When `signup_enabled` is true and `signup_token` exists, show:
  - The signup URL: `{baseURL}/signup/{signup_token}` (read-only `TextInput`)
  - A `CopyButton` to copy the URL (same pattern as the dashboard URL copy button)
  - A link to the public dashboard, greyed out / disabled if `dashboard_public` is off. Use a `Button` with `component="a"` and `disabled={!form.values.dashboard_public}` linking to `/tournaments/{dashboard_endpoint}/dashboard`

Add `signup_enabled`, `max_team_size` to the form's `initialValues` and the `updateTournament` call.

### Tournament service changes

`**frontend/src/services/tournament.tsx**` — update `updateTournament()` to include `signup_enabled` and `max_team_size` parameters.

### OpenAPI / type regeneration

After backend changes, regenerate the OpenAPI spec and frontend types:

```bash
cd backend && uv run ./cli.py generate-openapi
cd frontend && pnpm run openapi-ts
```

The new `SignupBody`, `SignupTournamentInfo`, etc. types will be auto-generated.

### i18n

Add new translation keys to `frontend/public/locales/en/common.json`:

```json
{
    "self_signup_title": "Self-Signup",
    "signup_enabled_label": "Allow players to sign up via a public link",
    "signup_url_label": "Signup URL",
    "signup_link_copied": "Copied Signup URL",
    "signup_copy_button": "Copy Signup URL",
    "max_team_size_label": "Maximum players per team",
    "signup_page_title": "Sign up for {{tournamentName}}",
    "signup_player_name_label": "Your name",
    "signup_player_name_placeholder": "Enter your name",
    "signup_team_action_label": "Team preference",
    "signup_join_team": "Join an existing team",
    "signup_create_team": "Create a new team",
    "signup_no_team": "No team (assign me later)",
    "signup_team_select_placeholder": "Select a team",
    "signup_team_name_label": "Team name",
    "signup_team_name_placeholder": "Enter team name",
    "signup_submit_button": "Sign Up",
    "signup_success_message": "You have been registered!",
    "signup_invalid_link": "This signup link is invalid or signup is closed.",
    "signup_tournament_full": "This tournament is full.",
    "signup_duplicate_name": "A player with this name already exists.",
    "signup_team_full": "This team is full.",
    "signup_view_dashboard": "View Public Dashboard"
}
```

Other locale files (`de`, `nl`, `fr`, etc.) only need the English keys added — they can be translated later.

## File Change Summary

### New files


| File                                                 | Purpose                               |
| ---------------------------------------------------- | ------------------------------------- |
| `backend/bracket/routes/signup.py`                   | Public signup API endpoints           |
| `backend/bracket/sql/signup.py`                      | Signup-related queries                |
| `backend/alembic/versions/<hash>_add_self_signup.py` | DB migration                          |
| `frontend/src/pages/signup.tsx`                      | Public signup page                    |
| `frontend/src/services/signup.tsx`                   | Unauthenticated API client for signup |


### Modified files


| File                                               | What changes                                                                   |
| -------------------------------------------------- | ------------------------------------------------------------------------------ |
| `backend/bracket/schema.py`                        | Add `signup_enabled`, `signup_token`, `max_team_size` columns to `tournaments` |
| `backend/bracket/models/db/tournament.py`          | Add fields to `TournamentInsertable`, `Tournament`, `TournamentUpdateBody`     |
| `backend/bracket/routes/tournaments.py`            | Generate `signup_token` on first enable                                        |
| `backend/bracket/routes/auth.py`                   | Add `tournament_by_signup_token` dependency                                    |
| `backend/bracket/routes/models.py`                 | Add `SignupInfoResponse` and related models                                    |
| `backend/bracket/app.py`                           | Register `signup.router`                                                       |
| `backend/bracket/utils/id_types.py`                | No changes needed (uses existing `TournamentId`, `TeamId`, `PlayerId`)         |
| `frontend/src/main.tsx`                            | Add `/signup/:signup_token` route                                              |
| `frontend/src/pages/tournaments/[id]/settings.tsx` | Add self-signup fieldset with toggle, URL, copy button, dashboard link         |
| `frontend/src/services/tournament.tsx`             | Add `signup_enabled`, `max_team_size` to `updateTournament()`                  |
| `frontend/public/locales/en/common.json`           | Add signup-related translation keys                                            |


## Implementation Order

1. **Migration + schema + models** — DB columns and Pydantic models
2. **SQL layer** — `sql/signup.py` with queries
3. **Auth dependency** — `tournament_by_signup_token` in `auth.py`
4. **Routes** — `routes/signup.py` with GET and POST endpoints
5. **Tournament update logic** — token generation on first enable in `routes/tournaments.py`
6. **Register router** — add to `app.py`
7. **OpenAPI regeneration** — `generate-openapi` + `openapi-ts`
8. **Frontend service** — `services/signup.tsx`
9. **Frontend signup page** — `pages/signup.tsx` with form, validation, success redirect
10. **Settings page** — add self-signup fieldset
11. **i18n** — translation keys
12. **Final Tests** — run backend tests, try the flow end-to-end

## Testing Notes

- Use red/green TDD.
- Backend tests live in `backend/tests/`. Run with `ENVIRONMENT=CI uv run pytest . -vvv`.
- Test the signup endpoints by creating a tournament with `signup_enabled=True`, then calling the public GET/POST endpoints with the token.
- Test edge cases: duplicate name, full team, full tournament (subscription limits), archived tournament, disabled signup, invalid token.
- Frontend: run `pnpm test` from `frontend/` for type checking and formatting.

