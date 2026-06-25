from decimal import Decimal

from heliclockter import datetime_utc

from bracket.logic.ranking.calculation import determine_ranking_for_stage_item
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.match import MatchState, MatchWithDetails, MatchWithDetailsDefinitive
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


def _ranking(tournament_id: TournamentId, now: datetime_utc, win: str, draw: str) -> Ranking:
    return Ranking(
        id=RankingId(-1),
        tournament_id=tournament_id,
        created=now,
        position=0,
        scoring_type=ScoringType.MATCH_POINTS,
        match_points=RankingMatchPointsData(
            win_points=Decimal(win),
            draw_points=Decimal(draw),
            loss_points=Decimal("0.0"),
        ),
    )


def test_determine_ranking_for_stage_item_elimination() -> None:
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
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )

    ranking = determine_ranking_for_stage_item(
        StageItemWithRounds(
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
                            stage_item_input1_score=2,
                            stage_item_input2_score=0,
                            state=MatchState.COMPLETED,
                        ),
                        MatchWithDetailsDefinitive(
                            id=MatchId(-2),
                            stage_item_input1=stage_item_input1,
                            stage_item_input2=stage_item_input2,
                            created=now,
                            duration_minutes=90,
                            round_id=RoundId(-1),
                            stage_item_input1_score=2,
                            stage_item_input2_score=2,
                            state=MatchState.COMPLETED,
                        ),
                        MatchWithDetails(  # This gets ignored in ranking calculation
                            id=MatchId(-3),
                            created=now,
                            duration_minutes=90,
                            round_id=RoundId(-1),
                            stage_item_input1_score=3,
                            stage_item_input2_score=2,
                            state=MatchState.IN_PROGRESS,
                        ),
                    ],
                    stage_item_id=StageItemId(-1),
                    created=now,
                    lifecycle_state=RoundLifecycleState.ACTIVE,
                    name="",
                )
            ],
            inputs=[stage_item_input1, stage_item_input2],
            type_name="Single Elimination",
            team_count=4,
            ranking_id=None,
            id=StageItemId(-1),
            stage_id=StageId(-1),
            name="",
            created=now,
            type=StageType.SINGLE_ELIMINATION,
        ),
        _ranking(tournament_id, now, win="3.5", draw="1.25"),
    )

    assert ranking == {
        -2: TeamStatistics(wins=0, draws=1, losses=1, points=Decimal("1.25")),
        -1: TeamStatistics(wins=1, draws=1, losses=0, points=Decimal("4.75")),
    }


def test_determine_ranking_for_stage_item_swiss() -> None:
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
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )

    ranking = determine_ranking_for_stage_item(
        StageItemWithRounds(
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
                            stage_item_input1_score=2,
                            stage_item_input2_score=0,
                            state=MatchState.COMPLETED,
                        ),
                        MatchWithDetailsDefinitive(
                            id=MatchId(-2),
                            stage_item_input1=stage_item_input1,
                            stage_item_input2=stage_item_input2,
                            created=now,
                            duration_minutes=90,
                            round_id=RoundId(-1),
                            stage_item_input1_score=2,
                            stage_item_input2_score=2,
                            state=MatchState.COMPLETED,
                        ),
                        MatchWithDetails(  # This gets ignored in ranking calculation
                            id=MatchId(-3),
                            created=now,
                            duration_minutes=90,
                            round_id=RoundId(-1),
                            stage_item_input1_score=3,
                            stage_item_input2_score=2,
                            state=MatchState.IN_PROGRESS,
                        ),
                    ],
                    stage_item_id=StageItemId(-1),
                    created=now,
                    lifecycle_state=RoundLifecycleState.ACTIVE,
                    name="",
                )
            ],
            inputs=[stage_item_input1, stage_item_input2],
            type_name="Swiss",
            team_count=4,
            ranking_id=None,
            id=StageItemId(-1),
            stage_id=StageId(-1),
            name="",
            created=now,
            type=StageType.SWISS,
        ),
        _ranking(tournament_id, now, win="3.5", draw="1.25"),
    )

    assert ranking == {
        -2: TeamStatistics(wins=0, draws=1, losses=1, points=Decimal("1208")),
        -1: TeamStatistics(wins=1, draws=1, losses=0, points=Decimal("1320")),
    }


def test_determine_ranking_for_stage_item_swiss_no_matches() -> None:
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
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )

    ranking = determine_ranking_for_stage_item(
        StageItemWithRounds(
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
            inputs=[stage_item_input1, stage_item_input2],
            type_name="Swiss",
            team_count=2,
            ranking_id=None,
            id=StageItemId(-1),
            stage_id=StageId(-1),
            name="",
            created=now,
            type=StageType.SWISS,
        ),
        _ranking(tournament_id, now, win="3.5", draw="1.25"),
    )

    assert ranking == {
        -2: TeamStatistics(wins=0, draws=0, losses=0, points=Decimal("1200")),
        -1: TeamStatistics(wins=0, draws=0, losses=0, points=Decimal("1200")),
    }
