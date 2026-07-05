"""Unit tests for build_team_stats_plan, the pure planner behind
recalculate_ranking_for_stage_item.
"""

from decimal import Decimal

from heliclockter import datetime_utc

from bracket.logic.plan import SetTeamStats
from bracket.logic.ranking.calculation import build_team_stats_plan
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.match import MatchState, MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking, RankingMatchPointsData, ScoringType
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.dummy_records import DUMMY_TEAM1, DUMMY_TEAM2
from bracket.utils.id_types import (
    MatchId,
    RankingId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)
from tests.unit_tests.mocks import match_sets_for_state


def test_build_team_stats_plan_produces_set_team_stats_for_round_robin() -> None:
    """build_team_stats_plan emits one SetTeamStats per concrete input, matching the stats that
    determine_ranking_for_stage_item computes (see ranking_calculation_test.py for the equivalent
    determine_ranking_for_stage_item assertions on the same fixture shape).
    """
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    stage_item_input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    stage_item_input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=2,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )

    stage_item = StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(-1),
                matches=[
                    MatchWithDetailsDefinitive(
                        id=MatchId(-1),
                        stage_item_input1=stage_item_input1,
                        stage_item_input2=stage_item_input2,
                        created=now,
                        duration_minutes=90,
                        round_id=RoundId(-1),
                        match_sets=match_sets_for_state(MatchId(0), MatchState.COMPLETED, 2, 0),
                    ),
                ],
                stage_item_id=StageItemId(-1),
                created=now,
                lifecycle_state=RoundLifecycleState.ACTIVE,
                name="",
            )
        ],
        inputs=[stage_item_input1, stage_item_input2],
        type_name="Round Robin",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.ROUND_ROBIN,
    )
    ranking = Ranking(
        id=RankingId(-1),
        tournament_id=tournament_id,
        created=now,
        position=0,
        scoring_type=ScoringType.MATCH_POINTS,
        match_points=RankingMatchPointsData(
            win_points=Decimal("3.0"),
            draw_points=Decimal("1.0"),
            loss_points=Decimal("0.0"),
        ),
    )

    plan = build_team_stats_plan(stage_item, ranking)

    # Deterministic order: build_team_stats_plan walks stage_item.inputs in order.
    assert plan == [
        SetTeamStats(
            stage_item_input_id=StageItemInputId(-1),
            stats=TeamStatistics(
                wins=1,
                draws=0,
                losses=0,
                points=Decimal("3.0"),
                set_difference=1,
                point_difference=2,
            ),
        ),
        SetTeamStats(
            stage_item_input_id=StageItemInputId(-2),
            stats=TeamStatistics(
                wins=0,
                draws=0,
                losses=1,
                points=Decimal("0.0"),
                set_difference=-1,
                point_difference=-2,
            ),
        ),
    ]


def test_build_team_stats_plan_skips_inputs_without_a_team() -> None:
    """A tentative/empty input (no team_id) never gets a SetTeamStats write."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    stage_item_input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )

    stage_item = StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(-1),
                matches=[],
                stage_item_id=StageItemId(-1),
                created=now,
                lifecycle_state=RoundLifecycleState.ACTIVE,
                name="",
            )
        ],
        inputs=[stage_item_input1],
        type_name="Round Robin",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.ROUND_ROBIN,
    )
    ranking = Ranking(
        id=RankingId(-1),
        tournament_id=tournament_id,
        created=now,
        position=0,
        scoring_type=ScoringType.MATCH_POINTS,
        match_points=RankingMatchPointsData(
            win_points=Decimal("3.0"),
            draw_points=Decimal("1.0"),
            loss_points=Decimal("0.0"),
        ),
    )

    plan = build_team_stats_plan(stage_item, ranking)

    assert plan == [
        SetTeamStats(stage_item_input_id=StageItemInputId(-1), stats=TeamStatistics()),
    ]
