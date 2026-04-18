# Implementation: Unscheduled Matches Lane in Planning View

## Goal

Add an "Unscheduled" lane on the left side of the planning/schedule page. It displays all matches that have no `court_id` / `start_time` / `position_in_schedule`. Users can drag matches from this lane onto court lanes (scheduling them), or drag scheduled matches back to unschedule them.

---

## Backend Changes

### 1. New endpoint: unschedule a match

**File:** `backend/bracket/routes/matches.py`

Add a `POST /tournaments/{tournament_id}/matches/{match_id}/unschedule` endpoint that sets `court_id = NULL`, `start_time = NULL`, `position_in_schedule = NULL` on the match, then reorders the remaining matches on the old court.

```python
@router.post(
    "/tournaments/{tournament_id}/matches/{match_id}/unschedule", response_model=SuccessResponse
)
async def unschedule_match(
    tournament_id: TournamentId,
    match_id: MatchId,
    tournament: Tournament = Depends(disallow_archived_tournament),
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    match = await sql_get_match(match_id)
    old_court_id = match.court_id

    await sql_unschedule_match(match_id)

    if old_court_id is not None:
        stages = await get_full_tournament_details(tournament_id)
        scheduled_matches = get_scheduled_matches(stages)
        await reorder_matches_for_court(tournament, scheduled_matches, old_court_id)

    await handle_conflicts(await get_full_tournament_details(tournament_id))
    return SuccessResponse()
```

Add the necessary imports: `sql_get_match` from `bracket.sql.matches`, `sql_unschedule_match` (new, see below), `handle_conflicts` from `bracket.logic.planning.conflicts`.

### 2. New SQL function: `sql_unschedule_match`

**File:** `backend/bracket/sql/matches.py`

```python
async def sql_unschedule_match(match_id: MatchId) -> None:
    query = """
        UPDATE matches
        SET court_id = NULL,
            start_time = NULL,
            position_in_schedule = NULL
        WHERE matches.id = :match_id
        """
    await database.execute(query=query, values={"match_id": match_id})
```

### 3. Modify `MatchRescheduleBody` to support scheduling from unscheduled

**File:** `backend/bracket/models/db/match.py`

Make `old_court_id` and `old_position` optional (nullable) so that dragging from the unscheduled lane works:

```python
class MatchRescheduleBody(BaseModelORM):
    old_court_id: CourtId | None = None
    old_position: int | None = None
    new_court_id: CourtId
    new_position: int
```

### 4. Update `handle_match_reschedule` for the new nullable fields

**File:** `backend/bracket/logic/planning/matches.py`

When `old_court_id` is `None`, the match is coming from the unscheduled pool. Skip the position/court validation for the old position. Instead, just find the match by `match_id` (it should have `court_id = None`), set its new court and position, and reorder only the `new_court_id`.

In the existing function, after the early return for same-position:

```python
async def handle_match_reschedule(
    tournament: Tournament, body: MatchRescheduleBody, match_id: MatchId
) -> None:
    if (
        body.old_position is not None
        and body.old_position == body.new_position
        and body.old_court_id == body.new_court_id
    ):
        return

    stages = await get_full_tournament_details(tournament.id)

    if body.old_court_id is None:
        # Match is being scheduled from unscheduled pool
        # Find the match and give it the new court + position
        all_matches = [
            MatchPosition(match=match, position=float(assert_some(match.position_in_schedule)))
            for stage in stages
            for stage_item in stage.stage_items
            for round_ in stage_item.rounds
            for match in round_.matches
            if match.start_time is not None and match.id != match_id
        ]
        # Add the newly scheduled match at the desired position
        target_match = next(
            match
            for stage in stages
            for stage_item in stage.stage_items
            for round_ in stage_item.rounds
            for match in round_.matches
            if match.id == match_id
        )
        offset = -0.5  # insert before existing match at that position
        all_matches.append(
            MatchPosition(
                match=target_match.model_copy(update={"court_id": body.new_court_id}),
                position=body.new_position + offset,
            )
        )
        await reorder_matches_for_court(tournament, all_matches, body.new_court_id)
        return

    # ... existing logic for court-to-court rescheduling unchanged ...
```

### 5. Regenerate OpenAPI spec

After the backend changes:

```bash
cd backend && uv run ./cli.py generate-openapi
```

Then regenerate the frontend types:

```bash
cd frontend && pnpm run openapi-ts
```

---

## Frontend Changes

### 1. Collect unscheduled matches

**File:** `frontend/src/services/lookups.tsx`

Add a function to get all unscheduled matches (those with `start_time == null`):

```typescript
export function getUnscheduledMatches(swrStagesResponse: SWRResponse): MatchWithDetails[] {
  const matches: MatchWithDetails[] = [];
  for (const stage of swrStagesResponse.data.data) {
    for (const stageItem of stage.stage_items) {
      for (const round of stageItem.rounds) {
        for (const match of round.matches) {
          if (match.start_time == null) {
            matches.push(match);
          }
        }
      }
    }
  }
  return matches;
}
```

### 2. Add unschedule API call

**File:** `frontend/src/services/match.tsx`

```typescript
export async function unscheduleMatch(tournament_id: number, match_id: number) {
  return createAxios()
    .post(`tournaments/${tournament_id}/matches/${match_id}/unschedule`)
    .catch((response: any) => handleRequestError(response));
}
```

### 3. Add the Unscheduled lane component and update drag logic

**File:** `frontend/src/pages/tournaments/[id]/schedule.tsx`

#### 3a. Define a sentinel droppable ID

Use a string constant like `"unscheduled"` as the `droppableId` for the unscheduled lane. This is distinct from numeric court IDs.

#### 3b. Create an `UnscheduledColumn` component

Render a `<Droppable droppableId="unscheduled">` containing `ScheduleRow` items for each unscheduled match. Style it to be visually distinct:

- Use a muted/dashed border or a different background color (e.g., `var(--mantine-color-gray-1)` in light mode, `var(--mantine-color-dark-6)` in dark mode).
- Use a fixed header like "Unscheduled" (add i18n key `unscheduled_title`).
- Same `25rem` width as court columns.

```tsx
function UnscheduledColumn({
  matches,
  openMatchModal,
  stageItemsLookup,
  matchesLookup,
}: {
  matches: MatchWithDetails[];
  openMatchModal: any;
  stageItemsLookup: any;
  matchesLookup: any;
}) {
  const { t } = useTranslation();
  const rows = matches.map((match, index) => (
    <ScheduleRow
      index={index}
      stageItemsLookup={stageItemsLookup}
      matchesLookup={matchesLookup}
      match={match}
      openMatchModal={openMatchModal}
      key={match.id}
    />
  ));

  const noItemsAlert =
    matches.length < 1 ? (
      <Alert icon={<IconAlertCircle size={16} />} title={t('all_matches_scheduled_title')} color="green" radius="md" mt="1rem">
        {t('all_matches_scheduled_description')}
      </Alert>
    ) : null;

  return (
    <Droppable droppableId="unscheduled" direction="vertical">
      {(provided) => (
        <div {...provided.droppableProps} ref={provided.innerRef}>
          <div
            style={{
              width: '25rem',
              padding: '1rem',
              borderRight: '2px dashed var(--mantine-color-gray-4)',
              backgroundColor: 'var(--mantine-color-gray-0)',
              borderRadius: '0.5rem',
              minHeight: '200px',
            }}
          >
            <h4 style={{ marginTop: 0, margin: 'auto' }}>{t('unscheduled_title')}</h4>
            {rows}
            {noItemsAlert}
            {provided.placeholder}
          </div>
        </div>
      )}
    </Droppable>
  );
}
```

Note: use Mantine's `useMantineColorScheme` or CSS variables to handle dark mode properly. The `gray-0` background won't work in dark mode — consider using `var(--mantine-color-dark-7)` in dark mode or using a Mantine `Paper` component with a `variant` instead.

#### 3c. Place the lane in the `Schedule` component

In the `Schedule` component, prepend the `UnscheduledColumn` before the court columns. Pass in the unscheduled matches. Add a visual separator (e.g., the dashed border on the column itself is sufficient, or add a `<Divider orientation="vertical" />` between the unscheduled lane and the court lanes).

#### 3d. Update `onDragEnd` handler

In `SchedulePage`, update the `DragDropContext.onDragEnd` handler to handle three scenarios:

1. **Court → Court** (existing): call `rescheduleMatch` as before.
2. **Unscheduled → Court**: call `rescheduleMatch` with `old_court_id: null, old_position: null` and `new_court_id` / `new_position` from the destination.
3. **Court → Unscheduled**: call `unscheduleMatch(tournamentId, matchId)`.
4. **Unscheduled → Unscheduled**: no-op (just reordering within the unscheduled pool is cosmetic only, no API call needed).

```typescript
onDragEnd={async ({ destination, source, draggableId: matchId }) => {
  if (destination == null || source == null) return;

  const fromUnscheduled = source.droppableId === 'unscheduled';
  const toUnscheduled = destination.droppableId === 'unscheduled';

  if (fromUnscheduled && toUnscheduled) {
    // Reordering within unscheduled — no-op
    return;
  }

  if (toUnscheduled) {
    // Court → Unscheduled
    await unscheduleMatch(tournamentData.id, +matchId);
  } else {
    // Court → Court OR Unscheduled → Court
    await rescheduleMatch(tournamentData.id, +matchId, {
      old_court_id: fromUnscheduled ? null : +source.droppableId,
      old_position: fromUnscheduled ? null : source.index,
      new_court_id: +destination.droppableId,
      new_position: destination.index,
    });
  }

  await swrStagesResponse.mutate();
}}
```

#### 3e. Pass unscheduled matches to `Schedule`

In `SchedulePage`, compute the unscheduled matches list and pass it as a prop:

```typescript
const unscheduledMatches = responseIsValid(swrStagesResponse)
  ? getUnscheduledMatches(swrStagesResponse)
  : [];
```

Then pass `unscheduledMatches` to `Schedule`, which passes it to `UnscheduledColumn`.

### 4. ScheduleRow: handle missing start_time badge

`ScheduleRow` currently renders a `<Time>` badge. In the unscheduled lane, `start_time` is null. The existing code already handles this (`match.start_time != null ? <Time ...> : null`), so no change needed — the badge just won't show.

### 5. i18n keys

**File:** `frontend/public/locales/en/common.json` (and other locale files)

Add:

```json
"unscheduled_title": "Unscheduled",
"all_matches_scheduled_title": "All scheduled",
"all_matches_scheduled_description": "All matches have been assigned to courts"
```

For other locales, add the English string as a placeholder — translators can update later.

---

## Testing

### Backend

Add a test in `backend/tests/integration_tests/api/rescheduling_matches_test.py`:

1. **Test unschedule**: Create a match with a court, call `POST .../unschedule`, verify `court_id`, `start_time`, and `position_in_schedule` are all `NULL`.
2. **Test schedule from unscheduled**: Create a match without a court, call `POST .../reschedule` with `old_court_id: null, old_position: null, new_court_id: X, new_position: 0`, verify the match is now on court X with position 0 and a start_time.

### Frontend

Manual testing:
1. Create a tournament with stages, stage items, rounds, and matches (use `create-dev-db`).
2. Create at least 2 courts.
3. Go to the Planning page — verify the unscheduled lane appears on the left with all unscheduled matches.
4. Click "Schedule All Unscheduled Matches" — verify matches move from the unscheduled lane to court lanes.
5. Drag a match from a court lane back to "Unscheduled" — verify it reappears in the unscheduled lane and disappears from the court.
6. Drag a match from "Unscheduled" to a court lane — verify it gets scheduled.
7. Drag matches between courts — verify existing behavior still works.

---

## Summary of files to change

| File | Change |
|---|---|
| `backend/bracket/sql/matches.py` | Add `sql_unschedule_match` |
| `backend/bracket/routes/matches.py` | Add `unschedule_match` endpoint |
| `backend/bracket/models/db/match.py` | Make `MatchRescheduleBody.old_court_id` and `old_position` optional |
| `backend/bracket/logic/planning/matches.py` | Handle `old_court_id=None` in `handle_match_reschedule` |
| `backend/tests/integration_tests/api/rescheduling_matches_test.py` | Add tests for unschedule + schedule-from-unscheduled |
| `frontend/src/services/lookups.tsx` | Add `getUnscheduledMatches` |
| `frontend/src/services/match.tsx` | Add `unscheduleMatch` |
| `frontend/src/pages/tournaments/[id]/schedule.tsx` | Add `UnscheduledColumn`, update `onDragEnd`, wire up unscheduled matches |
| `frontend/public/locales/*/common.json` | Add i18n keys |
| `backend/openapi/openapi.json` | Regenerate |
| `frontend/src/openapi/` | Regenerate |
