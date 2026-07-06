from fastapi import HTTPException
from heliclockter import datetime_utc

from bracket.logic.reconcile import reconcile_stage_item
from bracket.logic.scheduling.elimination import (
    build_single_elimination_stage_item,
    get_number_of_rounds_to_create_single_elimination,
)
from bracket.logic.scheduling.round_robin import (
    build_round_robin_stage_item,
    get_number_of_rounds_to_create_round_robin,
)
from bracket.logic.scheduling.standings_resolution import (
    get_standings_resolved_strategy,
    is_standings_resolved_stage_type,
)
from bracket.models.db.match import MatchCreateBody
from bracket.models.db.round import RoundInsertable, RoundLifecycleState
from bracket.models.db.stage_item import StageItem, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputFinal,
    StageItemInputOptionFinal,
    StageItemInputOptionTentative,
    StageItemInputTentative,
)
from bracket.models.db.team import FullTeamWithPlayers
from bracket.models.db.util import StageWithStageItems
from bracket.sql.matches import sql_create_match
from bracket.sql.rounds import get_next_round_name, sql_create_round
from bracket.sql.stage_items import get_stage_item
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import StageId, StageItemId, TournamentId
from tests.integration_tests.mocks import MOCK_NOW


async def create_rounds_for_new_stage_item(
    tournament_id: TournamentId, stage_item: StageItem
) -> None:
    # Standings-resolved stage items (e.g. Swiss) get their rounds from the placeholder skeleton
    # rather than an eager fixed count.
    if is_standings_resolved_stage_type(stage_item.type):
        return None

    rounds_count: int
    match stage_item.type:
        case StageType.ROUND_ROBIN:
            rounds_count = get_number_of_rounds_to_create_round_robin(stage_item.team_count)
        case StageType.SINGLE_ELIMINATION:
            rounds_count = get_number_of_rounds_to_create_single_elimination(stage_item.team_count)
        case other:
            raise NotImplementedError(f"No round creation implementation for {other}")

    for _ in range(rounds_count):
        await sql_create_round(
            RoundInsertable(
                created=MOCK_NOW,
                stage_item_id=stage_item.id,
                name=await get_next_round_name(tournament_id, stage_item.id),
            ),
        )


async def build_standings_resolved_placeholder_skeleton(
    tournament_id: TournamentId, stage_item: StageItem
) -> None:
    """Generate placeholder rounds and slot-matches for a standings-resolved stage item on creation.

    The round/match/bye structure comes from the stage type's registered skeleton builder.
    """
    strategy = get_standings_resolved_strategy(stage_item.type)
    if strategy is None or stage_item.games_per_player is None:
        return
    tournament = await sql_get_tournament(tournament_id)
    skeleton = strategy.skeleton_builder(stage_item.team_count, stage_item.games_per_player)
    for round_skeleton in skeleton.rounds:
        round_id = await sql_create_round(
            RoundInsertable(
                created=datetime_utc.now(),
                stage_item_id=stage_item.id,
                name=await get_next_round_name(tournament_id, stage_item.id),
                lifecycle_state=RoundLifecycleState.PLACEHOLDER,
            )
        )
        for slot1, slot2 in round_skeleton.matches:
            await sql_create_match(
                MatchCreateBody(
                    round_id=round_id,
                    court_id=None,
                    stage_item_input1_id=None,
                    stage_item_input2_id=None,
                    stage_item_input1_winner_from_match_id=None,
                    stage_item_input2_winner_from_match_id=None,
                    duration_minutes=tournament.duration_minutes,
                    custom_duration_minutes=None,
                    input1_slot=slot1,
                    input2_slot=slot2,
                    referee_slot=round_skeleton.bye_slot,
                )
            )


async def build_matches_for_stage_item(stage_item: StageItem, tournament_id: TournamentId) -> None:
    await create_rounds_for_new_stage_item(tournament_id, stage_item)
    stage_item_with_rounds = await get_stage_item(tournament_id, stage_item.id)

    if is_standings_resolved_stage_type(stage_item.type):
        await build_standings_resolved_placeholder_skeleton(tournament_id, stage_item)
        return None

    match stage_item.type:
        case StageType.ROUND_ROBIN:
            await build_round_robin_stage_item(tournament_id, stage_item_with_rounds)
        case StageType.SINGLE_ELIMINATION:
            await build_single_elimination_stage_item(tournament_id, stage_item_with_rounds)

        case _:
            raise HTTPException(
                400, f"Cannot automatically create matches for stage type {stage_item.type}"
            )

    await reconcile_stage_item(tournament_id, stage_item_with_rounds)


def determine_available_inputs(
    teams: list[FullTeamWithPlayers],
    stages: list[StageWithStageItems],
) -> dict[StageId, list[StageItemInputOptionTentative | StageItemInputOptionFinal]]:
    """
    Returns available inputs for the given stage.

    Inputs are either from:
    - Teams directly
    - Previous stage items of any type (tentative options)
    """
    all_team_options = {
        team.id: StageItemInputOptionFinal(team_id=team.id, already_taken=False) for team in teams
    }
    team_level_by_id = {team.id: team.level_id for team in teams}
    stage_level_by_stage_item_id = {
        stage_item.id: stage.level_id for stage in stages for stage_item in stage.stage_items
    }
    # Add inputs from stage items that can be used as outputs in the next phase.
    all_tentative_options = {
        (stage_item.id, winner_position): StageItemInputOptionTentative(
            winner_from_stage_item_id=stage_item.id,
            winner_position=winner_position,
            already_taken=False,
        )
        for stage in stages
        for stage_item in stage.stage_items
        for winner_position in range(1, stage_item.team_count + 1)
    }

    # Determine which inputs have been used (set `already_taken` to True)
    for stage in stages:
        for stage_item in stage.stage_items:
            for input_ in stage_item.inputs:
                match input_:
                    case StageItemInputFinal() as final if input_.team_id in all_team_options:
                        all_team_options[final.team_id].already_taken = True

                    case StageItemInputTentative() as tentative:
                        if (key := tentative.get_lookup_key()) in all_tentative_options:
                            all_tentative_options[key].already_taken = True

    # Loop through stage items once more to assemble the final results and make sure
    # tentative inputs are only available after the stage item that they originate from.
    # We start with all teams but not tentative inputs.
    results_tentative: dict[tuple[StageItemId, int], StageItemInputOptionTentative] = {}
    results = {}

    for stage in stages:
        results_teams = [
            option
            for team_id, option in all_team_options.items()
            if team_level_by_id[team_id] == stage.level_id
        ]
        same_level_tentative = [
            option
            for (stage_item_id, _), option in results_tentative.items()
            if stage_level_by_stage_item_id[stage_item_id] == stage.level_id
        ]
        results[stage.id] = results_teams + same_level_tentative

        # Add options for subsequent stage items for the tentative "outputs" from this round
        for stage_item in stage.stage_items:
            for (option_stage_item_id, option_win_pos), option in all_tentative_options.items():
                if option_stage_item_id == stage_item.id:
                    results_tentative[(option_stage_item_id, option_win_pos)] = option

    return results
