# Handoff: Pre-existing test fixture pollution causes 3 backend tests to fail in full-suite runs

## Symptom

Running the full backend test suite (`ENVIRONMENT=CI uv run pytest .` from `backend/`) on master
reproduces 3 failures. Each test passes when run individually, so these are test-ordering /
state-pollution bugs, not real product bugs:

1. `tests/integration_tests/api/tournaments_test.py::test_tournaments_endpoint`
2. `tests/integration_tests/api/tournaments_test.py::test_tournament_endpoint`
3. `tests/integration_tests/cronjobs/demo_user_deletion_test.py::test_delete_demo_accounts`

Verified pre-existing on commit `2a43443` — not caused by the issue #30 interleaving fix.

---

## Root cause #1 — `signup_test.py` mutates the session-scoped tournament without resetting it

`tests/integration_tests/api/signup_test.py` contains several tests that flip on signup for the
shared `auth_context.tournament`:

```python
await database.execute(
    query=tournaments.update()
    .where(tournaments.c.id == tournament_id)
    .values(signup_enabled=True, signup_token=signup_token),
)
```

None of them reset `signup_enabled` / `signup_token` afterwards. Once any signup test runs, the
session-scoped tournament permanently carries `signup_enabled=True` and a leaked token like
`'leveled-signup-join-team-token'`.

`test_tournaments_endpoint` and `test_tournament_endpoint` (in `tournaments_test.py`) then fail
with an assertion diff:

```
- 'signup_enabled': False,
+ 'signup_enabled': True,
- 'signup_token': None,
+ 'signup_token': 'leveled-signup-join-team-token',
```

### Fix sketch

Wrap each signup-enabling block in a try/finally (or context manager) that restores defaults:

```python
try:
    await database.execute(
        query=tournaments.update()
        .where(tournaments.c.id == tournament_id)
        .values(signup_enabled=True, signup_token=signup_token),
    )
    ...
finally:
    await database.execute(
        query=tournaments.update()
        .where(tournaments.c.id == tournament_id)
        .values(signup_enabled=False, signup_token=None),
    )
```

A small `enabled_signup(tournament_id, signup_token)` async context manager in
`tests/integration_tests/sql.py` would dedupe this across the ~6 signup tests that need it.

---

## Root cause #2 — `auth_context` fixture disconnects the shared DB when it tears down

`tests/integration_tests/conftest.py:61`:

```python
@pytest.fixture(scope="session")
async def auth_context(reinit_database: Database) -> AsyncIterator[AuthContext]:
    async with reinit_database, inserted_auth_context() as auth_context:
        yield auth_context
```

`async with reinit_database` calls `Database.__aexit__`, which **disconnects the connection
pool** when `auth_context` is torn down. `reinit_database` is also session-scoped and intends to
own the connection lifecycle itself, so this double-management is the bug.

`test_delete_demo_accounts` (`tests/integration_tests/cronjobs/demo_user_deletion_test.py`)
does not depend on the `auth_context` fixture — it calls `inserted_auth_context()` directly:

```python
async def test_delete_demo_accounts() -> None:
    async with inserted_auth_context() as auth_context:
        ...
```

When this test runs after any test that *did* use `auth_context`, pytest tears down
`auth_context` (since nothing else needs it), the embedded `async with reinit_database`
disconnects the pool, and the demo test's first `database.execute` blows up with
`AssertionError: DatabaseBackend is not running`.

### Fix sketch

Option A (smallest): drop `reinit_database` from the `async with` in `auth_context`. The
session-scoped autouse `reinit_database` already manages the connection lifecycle:

```python
@pytest.fixture(scope="session")
async def auth_context(reinit_database: Database) -> AsyncIterator[AuthContext]:
    async with inserted_auth_context() as auth_context:
        yield auth_context
```

Option B: change `test_delete_demo_accounts` to depend on the `auth_context` fixture so the
connection lifecycle matches the other integration tests. Less surgical, but probably fine.

---

## How to reproduce

```bash
cd backend
# Full suite — shows all 3 failures:
ENVIRONMENT=CI nix develop --command uv run pytest .

# Just root cause #1 — signup pollutes tournaments_test:
ENVIRONMENT=CI nix develop --command uv run pytest \
  tests/integration_tests/api/signup_test.py \
  tests/integration_tests/api/tournaments_test.py::test_tournaments_endpoint

# Just root cause #2 — auth_context teardown breaks demo test:
ENVIRONMENT=CI nix develop --command uv run pytest \
  tests/integration_tests/api/auth_test.py \
  tests/integration_tests/cronjobs/demo_user_deletion_test.py
```

Each test in isolation passes:

```bash
ENVIRONMENT=CI nix develop --command uv run pytest \
  tests/integration_tests/api/tournaments_test.py::test_tournaments_endpoint
ENVIRONMENT=CI nix develop --command uv run pytest \
  tests/integration_tests/cronjobs/demo_user_deletion_test.py
```

---

## Suggested order of attack

1. Fix the signup test cleanup (Root cause #1) — touches `signup_test.py` only, low risk.
2. Re-run the full suite to confirm the two tournament failures are gone.
3. Fix the auth_context fixture / demo test pairing (Root cause #2) — touches `conftest.py`
   (or just the demo test). Verify in isolation and as part of full suite.

There is also a benign trailing teardown error (`"DatabaseBackend is not running"`) printed on
the last test of any pytest invocation. It's the same root cause #2 surfacing in the
session-end teardown rather than mid-run; the option-A fix above should silence it.
