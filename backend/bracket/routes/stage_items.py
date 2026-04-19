from collections.abc import Iterable

from fastapi import APIRouter, Depends, HTTPException
from heliclockter import datetime_utc
from starlette import status

from bracket.config import config
from bracket.database import database
from bracket.logic.planning.conflicts import handle_conflicts
from bracket.logic.planning.matches import update_start_times_of_matches
from bracket.logic.planning.rounds import (
    MatchTimingAdjustmentInfeasible,
    get_all_scheduling_operations_for_swiss_round,
    get_draft_round,
)
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import (
    update_inputs_in_complete_elimination_stage_item,
)
from bracket.logic.scheduling.builder import (
    build_matches_for_stage_item,
)
from bracket.logic.scheduling.elimination import get_number_of_rounds_to_create_single_elimination
from bracket.logic.scheduling.round_robin import (
    get_number_of_rounds_to_create_round_robin,
    get_round_robin_combinations,
)
from bracket.logic.scheduling.upcoming_matches import get_upcoming_matches_for_swiss
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.match import MatchCreateBody, MatchFilter, MatchState, SuggestedMatch
from bracket.models.db.round import RoundInsertable
from bracket.models.db.stage_item import (
    StageItemActivateNextBody,
    StageItemCreateBody,
    StageItemUpdateBody,
    StageType,
)
from bracket.models.db.stage_item_inputs import StageItemInputEmpty
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import StageItemWithRounds
from bracket.routes.auth import (
    user_authenticated_for_tournament,
)
from bracket.routes.models import SuccessResponse
from bracket.routes.util import disallow_archived_tournament, stage_item_dependency
from bracket.sql.courts import get_all_courts_in_tournament
from bracket.sql.matches import (
    sql_create_match,
    sql_delete_matches,
    sql_reschedule_match_and_determine_duration_and_margin,
)
from bracket.sql.rounds import (
    get_next_round_name,
    get_round_by_id,
    set_round_active_or_draft,
    sql_create_round,
    sql_delete_rounds_for_stage_item_id,
)
from bracket.sql.shared import (
    sql_delete_stage_item_matches,
    sql_delete_stage_item_with_foreign_keys,
)
from bracket.sql.stage_items import (
    get_stage_item,
    sql_create_stage_item_with_empty_inputs,
)
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.errors import (
    ForeignKey,
    check_foreign_key_violation,
)
from bracket.utils.id_types import StageItemId, TournamentId

router = APIRouter(prefix=config.api_prefix)


def is_empty_input_slot(input_: object) -> bool:
    return isinstance(input_, StageItemInputEmpty)


def format_slots(slots: Iterable[int]) -> str:
    return ", ".join(str(slot) for slot in sorted(slots))


async def update_stage_item_input_slots(
    stage_item_id: StageItemId, input_ids_in_slot_order: list[int]
) -> None:
    for index, stage_item_input_id in enumerate(input_ids_in_slot_order, start=1):
        await database.execute(
            query="""
                UPDATE stage_item_inputs
                SET slot = :slot
                WHERE stage_item_id = :stage_item_id
                AND id = :stage_item_input_id
            """,
            values={
                "slot": index,
                "stage_item_id": stage_item_id,
                "stage_item_input_id": stage_item_input_id,
            },
        )


async def append_empty_stage_item_inputs(
    tournament_id: TournamentId, stage_item_id: StageItemId, start_slot: int, end_slot: int
) -> None:
    for slot in range(start_slot, end_slot + 1):
        await database.execute(
            query="""
                INSERT INTO stage_item_inputs (slot, tournament_id, stage_item_id)
                VALUES (:slot, :tournament_id, :stage_item_id)
            """,
            values={
                "slot": slot,
                "tournament_id": tournament_id,
                "stage_item_id": stage_item_id,
            },
        )


async def update_stage_item_row(
    stage_item_id: StageItemId, stage_item_body: StageItemUpdateBody
) -> None:
    await database.execute(
        query="""
            UPDATE stage_items
            SET name = :name,
                ranking_id = :ranking_id,
                team_count = :team_count
            WHERE stage_items.id = :stage_item_id
        """,
        values={
            "stage_item_id": stage_item_id,
            "name": stage_item_body.name,
            "ranking_id": stage_item_body.ranking_id,
            "team_count": stage_item_body.team_count,
        },
    )


def get_removed_match_ids_and_blocking_slots(
    stage_item: StageItemWithRounds, removable_input_ids: set[int]
) -> tuple[list[int], set[int]]:
    removable_match_ids: list[int] = []
    blocking_slots: set[int] = set()
    slot_by_input_id = {
        input_.id: input_.slot for input_ in stage_item.inputs if input_.id is not None
    }

    for round_ in stage_item.rounds:
        for match in round_.matches:
            involved_input_ids = {
                match.stage_item_input1_id,
                match.stage_item_input2_id,
            } & removable_input_ids
            if len(involved_input_ids) < 1:
                continue

            if match.state in {MatchState.IN_PROGRESS, MatchState.COMPLETED}:
                blocking_slots.update(
                    slot_by_input_id[input_id]
                    for input_id in involved_input_ids
                    if input_id is not None
                )
                continue

            removable_match_ids.append(match.id)

    return removable_match_ids, blocking_slots


async def clear_removed_winner_positions(stage_item_id: StageItemId, new_team_count: int) -> None:
    await database.execute(
        query="""
            UPDATE stage_item_inputs
            SET team_id = NULL,
                winner_from_stage_item_id = NULL,
                winner_position = NULL
            WHERE winner_from_stage_item_id = :stage_item_id
            AND winner_position > :new_team_count
        """,
        values={"stage_item_id": stage_item_id, "new_team_count": new_team_count},
    )


async def ensure_round_count_for_round_robin(
    tournament_id: TournamentId, stage_item_id: StageItemId, team_count: int
) -> None:
    stage_item = await get_stage_item(tournament_id, stage_item_id)
    expected_round_count = get_number_of_rounds_to_create_round_robin(team_count)
    while len(stage_item.rounds) < expected_round_count:
        await sql_create_round(
            RoundInsertable(
                created=datetime_utc.now(),
                is_draft=False,
                stage_item_id=stage_item_id,
                name=await get_next_round_name(tournament_id, stage_item_id),
            )
        )
        stage_item = await get_stage_item(tournament_id, stage_item_id)


async def add_missing_round_robin_matches(
    tournament_id: TournamentId, stage_item_id: StageItemId, team_count: int
) -> None:
    await ensure_round_count_for_round_robin(tournament_id, stage_item_id, team_count)
    stage_item = await get_stage_item(tournament_id, stage_item_id)
    tournament = await sql_get_tournament(tournament_id)
    existing_pairs = {
        frozenset({match.stage_item_input1_id, match.stage_item_input2_id})
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.stage_item_input1_id is not None and match.stage_item_input2_id is not None
    }

    for round_index, combinations in enumerate(get_round_robin_combinations(team_count)):
        round_ = stage_item.rounds[round_index]
        for team_1_index, team_2_index in combinations:
            if team_1_index >= team_count or team_2_index >= team_count:
                continue

            input_1 = stage_item.inputs[team_1_index]
            input_2 = stage_item.inputs[team_2_index]
            pair = frozenset({input_1.id, input_2.id})
            if pair in existing_pairs:
                continue

            await sql_create_match(
                MatchCreateBody(
                    round_id=round_.id,
                    stage_item_input1_id=input_1.id,
                    stage_item_input2_id=input_2.id,
                    stage_item_input1_winner_from_match_id=None,
                    stage_item_input2_winner_from_match_id=None,
                    court_id=None,
                    duration_minutes=tournament.duration_minutes,
                    margin_minutes=tournament.margin_minutes,
                    custom_duration_minutes=None,
                    custom_margin_minutes=None,
                )
            )
            existing_pairs.add(pair)


async def resize_single_elimination_stage_item(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item: StageItemWithRounds,
    new_team_count: int,
) -> None:
    if any(
        match.state is not MatchState.NOT_STARTED
        for round_ in stage_item.rounds
        for match in round_.matches
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot change player count for a single-elimination stage item "
                "after games have started"
            ),
        )

    old_team_count = stage_item.team_count
    if new_team_count < old_team_count:
        slots_to_remove = old_team_count - new_team_count
        empty_inputs = sorted(
            (input_ for input_ in stage_item.inputs if is_empty_input_slot(input_)),
            key=lambda input_: input_.slot,
            reverse=True,
        )
        if len(empty_inputs) < slots_to_remove:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reduce player count until {slots_to_remove} slot(s) are empty",
            )

        inputs_to_remove = empty_inputs[:slots_to_remove]
        removable_input_ids = {input_.id for input_ in inputs_to_remove if input_.id is not None}
        _, blocking_slots = get_removed_match_ids_and_blocking_slots(
            stage_item, removable_input_ids
        )
        if len(blocking_slots) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Cannot reduce player count because slot "
                    f"{format_slots(blocking_slots)} is used by matches that are "
                    "already in progress or completed"
                ),
            )

        await database.execute(
            query="""
                DELETE FROM stage_item_inputs
                WHERE stage_item_id = :stage_item_id
                AND id = ANY(:stage_item_input_ids)
            """,
            values={
                "stage_item_id": stage_item_id,
                "stage_item_input_ids": list(removable_input_ids),
            },
        )

        remaining_input_ids = [
            input_.id
            for input_ in sorted(stage_item.inputs, key=lambda input_: input_.slot)
            if input_.id not in removable_input_ids
        ]
        await update_stage_item_input_slots(stage_item_id, remaining_input_ids)
    elif new_team_count > old_team_count:
        await append_empty_stage_item_inputs(
            tournament_id, stage_item_id, old_team_count + 1, new_team_count
        )

    await clear_removed_winner_positions(stage_item_id, new_team_count)
    await sql_delete_stage_item_matches(stage_item_id)
    await sql_delete_rounds_for_stage_item_id(stage_item_id)


async def resize_non_elimination_stage_item(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item: StageItemWithRounds,
    new_team_count: int,
) -> None:
    old_team_count = stage_item.team_count
    if new_team_count > old_team_count:
        await append_empty_stage_item_inputs(
            tournament_id, stage_item_id, old_team_count + 1, new_team_count
        )
        return

    slots_to_remove = old_team_count - new_team_count
    empty_inputs = sorted(
        (input_ for input_ in stage_item.inputs if is_empty_input_slot(input_)),
        key=lambda input_: input_.slot,
        reverse=True,
    )
    if len(empty_inputs) < slots_to_remove:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reduce player count until {slots_to_remove} slot(s) are empty",
        )

    inputs_to_remove = empty_inputs[:slots_to_remove]
    removable_input_ids = {input_.id for input_ in inputs_to_remove if input_.id is not None}
    removable_match_ids, blocking_slots = get_removed_match_ids_and_blocking_slots(
        stage_item, removable_input_ids
    )
    if len(blocking_slots) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot reduce player count because slot "
                f"{format_slots(blocking_slots)} is used by matches that are already "
                "in progress or completed"
            ),
        )

    await sql_delete_matches(removable_match_ids)
    await database.execute(
        query="""
            DELETE FROM stage_item_inputs
            WHERE stage_item_id = :stage_item_id
            AND id = ANY(:stage_item_input_ids)
        """,
        values={
            "stage_item_id": stage_item_id,
            "stage_item_input_ids": list(removable_input_ids),
        },
    )

    remaining_input_ids = [
        input_.id
        for input_ in sorted(stage_item.inputs, key=lambda input_: input_.slot)
        if input_.id not in removable_input_ids
    ]
    await update_stage_item_input_slots(stage_item_id, remaining_input_ids)
    await clear_removed_winner_positions(stage_item_id, new_team_count)


async def resize_stage_item_if_needed(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item: StageItemWithRounds,
    stage_item_body: StageItemUpdateBody,
) -> None:
    if stage_item_body.team_count == stage_item.team_count:
        return

    if stage_item.type is StageType.SINGLE_ELIMINATION:
        get_number_of_rounds_to_create_single_elimination(stage_item_body.team_count)
        await resize_single_elimination_stage_item(
            tournament_id, stage_item_id, stage_item, stage_item_body.team_count
        )
        return

    await resize_non_elimination_stage_item(
        tournament_id, stage_item_id, stage_item, stage_item_body.team_count
    )


@router.delete(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}", response_model=SuccessResponse
)
async def delete_stage_item(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: StageItemWithRounds = Depends(stage_item_dependency),
) -> SuccessResponse:
    with check_foreign_key_violation(
        {ForeignKey.matches_stage_item_input1_id_fkey, ForeignKey.matches_stage_item_input2_id_fkey}
    ):
        await sql_delete_stage_item_with_foreign_keys(stage_item_id)
    await update_start_times_of_matches(tournament_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stage_items", response_model=SuccessResponse)
async def create_stage_item(
    tournament_id: TournamentId,
    stage_body: StageItemCreateBody,
    user: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    await check_foreign_keys_belong_to_tournament(stage_body, tournament_id)

    stages = await get_full_tournament_details(tournament_id)
    existing_stage_items = [stage_item for stage in stages for stage_item in stage.stage_items]
    check_requirement(existing_stage_items, user, "max_stage_items")

    stage_item = await sql_create_stage_item_with_empty_inputs(tournament_id, stage_body)
    await build_matches_for_stage_item(stage_item, tournament_id)
    return SuccessResponse()


@router.put(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}", response_model=SuccessResponse
)
async def update_stage_item(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item_body: StageItemUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    stage_item: StageItemWithRounds = Depends(stage_item_dependency),
) -> SuccessResponse:
    if stage_item is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not find all stages",
        )

    await check_foreign_keys_belong_to_tournament(stage_item_body, tournament_id)
    team_count_changed = stage_item_body.team_count != stage_item.team_count

    async with database.transaction():
        await resize_stage_item_if_needed(tournament_id, stage_item_id, stage_item, stage_item_body)
        await update_stage_item_row(stage_item_id, stage_item_body)

        if team_count_changed and stage_item.type is StageType.ROUND_ROBIN:
            await add_missing_round_robin_matches(
                tournament_id, stage_item_id, stage_item_body.team_count
            )
        elif team_count_changed and stage_item.type is StageType.SINGLE_ELIMINATION:
            updated_stage_item = await get_stage_item(tournament_id, stage_item_id)
            await build_matches_for_stage_item(updated_stage_item, tournament_id)

    updated_stage_item = await get_stage_item(tournament_id, stage_item_id)
    await recalculate_ranking_for_stage_item(tournament_id, updated_stage_item)
    if updated_stage_item.type == StageType.SINGLE_ELIMINATION:
        await update_inputs_in_complete_elimination_stage_item(updated_stage_item)
    if team_count_changed:
        await update_start_times_of_matches(tournament_id)
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}/start_next_round",
    response_model=SuccessResponse,
)
async def start_next_round(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    active_next_body: StageItemActivateNextBody,
    stage_item: StageItemWithRounds = Depends(stage_item_dependency),
    user: UserPublic = Depends(user_authenticated_for_tournament),
    elo_diff_threshold: int = 200,
    iterations: int = 2_000,
    only_recommended: bool = False,
    _: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    draft_round = get_draft_round(stage_item)
    if draft_round is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="There is already a draft round in this stage item, please delete it first",
        )

    match_filter = MatchFilter(
        elo_diff_threshold=elo_diff_threshold,
        only_recommended=only_recommended,
        limit=1,
        iterations=iterations,
    )
    all_matches_to_schedule = get_upcoming_matches_for_swiss(match_filter, stage_item)
    if len(all_matches_to_schedule) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No more matches to schedule, all combinations of teams have been added already",
        )

    stages = await get_full_tournament_details(tournament_id)
    existing_rounds = [
        round_
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
    ]
    check_requirement(existing_rounds, user, "max_rounds")

    round_id = await sql_create_round(
        RoundInsertable(
            created=datetime_utc.now(),
            is_draft=True,
            stage_item_id=stage_item_id,
            name=await get_next_round_name(tournament_id, stage_item_id),
        ),
    )
    draft_round = await get_round_by_id(tournament_id, round_id)
    tournament = await sql_get_tournament(tournament_id)
    courts = await get_all_courts_in_tournament(tournament_id)

    limit = len(courts) - len(draft_round.matches)
    for ___ in range(limit):
        stage_item = await get_stage_item(tournament_id, stage_item_id)
        draft_round = next(round_ for round_ in stage_item.rounds if round_.is_draft)
        all_matches_to_schedule = get_upcoming_matches_for_swiss(
            match_filter, stage_item, draft_round
        )
        if len(all_matches_to_schedule) < 1:
            break

        match = all_matches_to_schedule[0]
        assert isinstance(match, SuggestedMatch)

        assert draft_round.id and match.stage_item_input1.id and match.stage_item_input2.id
        await sql_create_match(
            MatchCreateBody(
                round_id=draft_round.id,
                stage_item_input1_id=match.stage_item_input1.id,
                stage_item_input2_id=match.stage_item_input2.id,
                court_id=None,
                stage_item_input1_winner_from_match_id=None,
                stage_item_input2_winner_from_match_id=None,
                duration_minutes=tournament.duration_minutes,
                margin_minutes=tournament.margin_minutes,
                custom_duration_minutes=None,
                custom_margin_minutes=None,
            ),
        )

    draft_round = await get_round_by_id(tournament_id, round_id)
    try:
        stages = await get_full_tournament_details(tournament_id)
        court_ids = [court.id for court in courts]

        rescheduling_operations = get_all_scheduling_operations_for_swiss_round(
            court_ids, stages, tournament, draft_round.matches, active_next_body.adjust_to_time
        )

        # TODO: if safe: await asyncio.gather(*rescheduling_operations)
        for op in rescheduling_operations:
            await sql_reschedule_match_and_determine_duration_and_margin(*op)
    except MatchTimingAdjustmentInfeasible as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await set_round_active_or_draft(draft_round.id, tournament_id, is_draft=False)
    await handle_conflicts(await get_full_tournament_details(tournament_id))
    return SuccessResponse()
