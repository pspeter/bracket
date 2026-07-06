import math
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from bracket.logic.apply_plan import apply_plan
from bracket.logic.plan import PlanItem, SetTeamStats
from bracket.logic.ranking.statistics import START_ELO, TeamStatistics
from bracket.models.db.match import MatchState, MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking, ScoringType
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.util import StageItemWithRounds, is_round_complete
from bracket.sql.rankings import get_ranking_for_stage_item
from bracket.utils.id_types import StageItemInputId, TournamentId

K = 32
D = 400


def set_statistics_for_stage_item_input(
    team_index: int,
    stats: defaultdict[StageItemInputId, TeamStatistics],
    match: MatchWithDetailsDefinitive,
    stage_item_input_id: StageItemInputId,
    ranking: Ranking,
    stage_item: StageItemWithRounds,
) -> None:
    is_team1 = team_index == 0
    # Win/draw/loss is decided by sets won. For a single-set match this is identical to comparing
    # the two flat scores, so num_sets=1 behaves exactly as before.
    sets1 = match.sets_won_by_input1
    sets2 = match.sets_won_by_input2
    team_sets = sets1 if is_team1 else sets2
    opp_sets = sets2 if is_team1 else sets1
    was_draw = sets1 == sets2
    has_won = not was_draw and team_sets == max(sets1, sets2)

    completed_sets = match.completed_sets
    if is_team1:
        total_points_for = sum(s.stage_item_input1_score for s in completed_sets)
        total_points_against = sum(s.stage_item_input2_score for s in completed_sets)
    else:
        total_points_for = sum(s.stage_item_input2_score for s in completed_sets)
        total_points_against = sum(s.stage_item_input1_score for s in completed_sets)

    stats[stage_item_input_id].set_difference += team_sets - opp_sets
    stats[stage_item_input_id].point_difference += total_points_for - total_points_against

    if has_won:
        stats[stage_item_input_id].wins += 1
    elif was_draw:
        stats[stage_item_input_id].draws += 1
    else:
        stats[stage_item_input_id].losses += 1

    match stage_item.type:
        case StageType.ROUND_ROBIN | StageType.SINGLE_ELIMINATION:
            match ranking.scoring_type:
                case ScoringType.MATCH_POINTS:
                    mp = ranking.match_points
                    if has_won:
                        stats[stage_item_input_id].points += mp.win_points if mp else Decimal("1.0")
                    elif was_draw:
                        stats[stage_item_input_id].points += (
                            mp.draw_points if mp else Decimal("0.5")
                        )
                    else:
                        stats[stage_item_input_id].points += (
                            mp.loss_points if mp else Decimal("0.0")
                        )

                case ScoringType.SET_POINTS:
                    stats[stage_item_input_id].points += Decimal(team_sets)

                case ScoringType.SET_POINTS_WITH_MATCH_BONUS:
                    stats[stage_item_input_id].points += Decimal(team_sets)
                    if has_won:
                        # Subtype row should always exist for this scoring type, but fall back to
                        # the model default bonus rather than crashing if it is ever missing.
                        bonus = ranking.set_points_with_bonus
                        stats[stage_item_input_id].points += (
                            bonus.match_bonus_points if bonus is not None else Decimal("1.0")
                        )

        case StageType.SWISS:
            # Swiss ELO uses match_points.win/draw/loss or standard 1.0/0.5/0.0 for set-based types
            if ranking.match_points is not None:
                if has_won:
                    elo_score = ranking.match_points.win_points
                elif was_draw:
                    elo_score = ranking.match_points.draw_points
                else:
                    elo_score = ranking.match_points.loss_points
            else:
                elo_score = (
                    Decimal("1.0") if has_won else Decimal("0.5") if was_draw else Decimal("0.0")
                )
            rating_diff = (match.stage_item_input2.elo - match.stage_item_input1.elo) * (
                1 if is_team1 else -1
            )
            expected_score = Decimal(1.0 / (1.0 + math.pow(10.0, rating_diff / D)))
            stats[stage_item_input_id].points += int(K * (elo_score - expected_score))

        case StageType.MEXICANO:
            # Mexicano standings are hardwired to cumulative points scored, summed over every
            # completed set of every completed match, from a zero baseline.
            stats[stage_item_input_id].points += Decimal(total_points_for)

        case _:
            raise ValueError(f"Unsupported stage type: {stage_item.type}")


def _apply_mexicano_bye_compensation(
    stage_item: StageItemWithRounds,
    stats: defaultdict[StageItemInputId, TeamStatistics],
) -> None:
    """Bank a round's average points-scored for every currently-active input absent from it.

    A round only compensates once every match in it is COMPLETED, and only currently-active
    inputs (``StageItemInputFinal.team.active``) that appear in none of that round's playing
    slots (``stage_item_input1``/``stage_item_input2``) receive it -- detection is deliberately
    by absence from the playing slots, not the referee slot, which is a general-purpose feature
    and not a reliable bye marker. Once a round is fully completed its compensation is fixed:
    later rounds cannot change it, since this only ever reads from already-completed rounds.

    A resolved round can also contain a match that was never assigned a pairing at all --
    cleared to [None, None] rather than played -- when a mid-tournament deactivation shrank the
    active field below the round's pre-built skeleton capacity (issue #261). ``is_round_complete``
    treats that surplus match as vacuously settled so the round's real matches still compensate
    once completed; it is simply skipped when collecting playing points/ids below.
    """
    active_ids = {
        input_.id
        for input_ in stage_item.inputs
        if not isinstance(input_, StageItemInputFinal) or input_.team.active
    }

    for round_ in stage_item.rounds:
        matches = round_.matches
        if not is_round_complete(round_):
            continue

        playing_points: list[Decimal] = []
        playing_ids: set[StageItemInputId] = set()
        for match in matches:
            if not isinstance(match, MatchWithDetailsDefinitive):
                continue
            if match.state is not MatchState.COMPLETED:
                continue
            completed_sets = match.completed_sets
            playing_points.append(Decimal(sum(s.stage_item_input1_score for s in completed_sets)))
            playing_points.append(Decimal(sum(s.stage_item_input2_score for s in completed_sets)))
            playing_ids.add(match.stage_item_input1.id)
            playing_ids.add(match.stage_item_input2.id)

        if not playing_points:
            continue

        round_average = (sum(playing_points, Decimal(0)) / len(playing_points)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        for input_id in active_ids - playing_ids:
            stats[input_id].points += round_average


def determine_ranking_for_stage_item(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
) -> defaultdict[StageItemInputId, TeamStatistics]:
    input_x_stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)

    if stage_item.type is StageType.SWISS:
        for input_ in stage_item.inputs:
            input_x_stats[input_.id].points = START_ELO

    matches = [
        match
        for round_ in stage_item.rounds
        for match in round_.matches
        if isinstance(match, MatchWithDetailsDefinitive)
        if match.state is MatchState.COMPLETED
    ]
    for match in matches:
        for team_index, stage_item_input in enumerate(match.stage_item_inputs):
            set_statistics_for_stage_item_input(
                team_index,
                input_x_stats,
                match,
                stage_item_input.id,
                ranking,
                stage_item,
            )

    if stage_item.type is StageType.MEXICANO:
        _apply_mexicano_bye_compensation(stage_item, input_x_stats)

    return input_x_stats


def determine_team_ranking_for_stage_item(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
) -> list[tuple[StageItemInputId, TeamStatistics]]:
    team_ranking = determine_ranking_for_stage_item(stage_item, ranking)
    return sorted(
        team_ranking.items(),
        key=lambda x: (x[1].points, x[1].set_difference, x[1].point_difference),
        reverse=True,
    )


def build_team_stats_plan(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
) -> list[PlanItem]:
    """Compute the ``SetTeamStats`` writes for every concrete input of ``stage_item``."""
    stats_per_input = determine_ranking_for_stage_item(stage_item, ranking)
    return [
        SetTeamStats(
            stage_item_input_id=stage_item_input.id,
            stats=stats_per_input[stage_item_input.id],
        )
        for stage_item_input in stage_item.inputs
        if stage_item_input.team_id is not None
    ]


async def recalculate_ranking_for_stage_item(
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    ranking = await get_ranking_for_stage_item(tournament_id, stage_item.id)
    assert stage_item, "Stage item not found"
    assert ranking, "Ranking not found"

    plan = build_team_stats_plan(stage_item, ranking)
    await apply_plan(tournament_id, plan)
