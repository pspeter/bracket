"""Unit tests for Mexicano bye compensation in ranking calculation (issue #260).

Split out of ``ranking_calculation_test.py`` to keep that module under the project's line-count
lint threshold. Covers the round-average compensation banked by any currently-active input absent
from a fully-completed round's playing slots -- including a round-1 bye, multiple simultaneous
sitters in one round, compensation staying fixed once a round completes, and incomplete rounds
contributing no compensation.
"""

from decimal import Decimal
from typing import Any

from heliclockter import datetime_utc

from bracket.logic.ranking.calculation import determine_ranking_for_stage_item
from bracket.models.db.match import MatchState, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking, RankingMatchPointsData, ScoringType
from bracket.models.db.round import RoundLifecycleState
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.dummy_records import DUMMY_TEAM1
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


def _make_sets(match_id: MatchId, scores: list[tuple[int, int]]) -> list[Any]:
    from bracket.models.db.match import MatchSet, MatchSetState
    from bracket.utils.id_types import MatchSetId

    return [
        MatchSet(
            id=MatchSetId(int(match_id) * 10 + i),
            match_id=match_id,
            set_number=i + 1,
            stage_item_input1_score=s1,
            stage_item_input2_score=s2,
            state=MatchSetState.COMPLETED,
        )
        for i, (s1, s2) in enumerate(scores)
    ]


def _mexicano_input(input_id: int, slot: int, tournament_id: TournamentId) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(input_id),
        team_id=TeamId(input_id),
        slot=slot,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(input_id)),
    )


def test_mexicano_bye_compensation_banks_the_round_average_for_the_sitter() -> None:
    """A round-1 bye (odd entrant count) banks the mean of points scored by that round's players."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    i1 = _mexicano_input(-1, 1, tournament_id)
    i2 = _mexicano_input(-2, 2, tournament_id)
    i3 = _mexicano_input(-3, 3, tournament_id)
    i4 = _mexicano_input(-4, 4, tournament_id)
    i5 = _mexicano_input(-5, 5, tournament_id)  # sits out round 1

    match_a = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=i1,
        stage_item_input2=i2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=_make_sets(MatchId(-1), [(21, 10)]),
    )
    match_b = MatchWithDetailsDefinitive(
        id=MatchId(-2),
        stage_item_input1=i3,
        stage_item_input2=i4,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=_make_sets(MatchId(-2), [(15, 18)]),
    )

    stage_item = StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(-1),
                matches=[match_a, match_b],
                stage_item_id=StageItemId(-1),
                created=now,
                lifecycle_state=RoundLifecycleState.LOCKED,
                name="",
            )
        ],
        inputs=[i1, i2, i3, i4, i5],
        type_name="Mexicano",
        team_count=5,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.MEXICANO,
    )

    result = determine_ranking_for_stage_item(
        stage_item, _ranking(tournament_id, now, win="3.0", draw="1.0")
    )
    # Points scored: 21, 10, 15, 18 -> mean 16.
    assert result[StageItemInputId(-1)].points == Decimal("21")
    assert result[StageItemInputId(-2)].points == Decimal("10")
    assert result[StageItemInputId(-3)].points == Decimal("15")
    assert result[StageItemInputId(-4)].points == Decimal("18")
    assert result[StageItemInputId(-5)].points == Decimal("16")


def test_mexicano_bye_compensation_supports_multiple_sitters_in_one_round() -> None:
    """More than one currently-active input can be absent from a round's playing slots at once;
    every one of them banks that round's average."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    i1 = _mexicano_input(-1, 1, tournament_id)
    i2 = _mexicano_input(-2, 2, tournament_id)
    i3 = _mexicano_input(-3, 3, tournament_id)  # sits out
    i4 = _mexicano_input(-4, 4, tournament_id)  # sits out

    match_a = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=i1,
        stage_item_input2=i2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=_make_sets(MatchId(-1), [(20, 12)]),
    )

    stage_item = StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(-1),
                matches=[match_a],
                stage_item_id=StageItemId(-1),
                created=now,
                lifecycle_state=RoundLifecycleState.LOCKED,
                name="",
            )
        ],
        inputs=[i1, i2, i3, i4],
        type_name="Mexicano",
        team_count=4,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.MEXICANO,
    )

    result = determine_ranking_for_stage_item(
        stage_item, _ranking(tournament_id, now, win="3.0", draw="1.0")
    )
    # Points scored: 20, 12 -> mean 16, banked by both sitters.
    assert result[StageItemInputId(-1)].points == Decimal("20")
    assert result[StageItemInputId(-2)].points == Decimal("12")
    assert result[StageItemInputId(-3)].points == Decimal("16")
    assert result[StageItemInputId(-4)].points == Decimal("16")


def test_mexicano_bye_compensation_is_fixed_once_round_completes() -> None:
    """A later round's results never retroactively change an earlier round's compensation."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    i1 = _mexicano_input(-1, 1, tournament_id)
    i2 = _mexicano_input(-2, 2, tournament_id)
    i3 = _mexicano_input(-3, 3, tournament_id)  # sits out round 1, plays round 2

    round1_match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=i1,
        stage_item_input2=i2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=_make_sets(MatchId(-1), [(20, 10)]),  # round-1 average = 15
    )
    # Round 2: i3 now plays (against i1) and scores far more than round 1's average, but that
    # must not change what i3 already banked for sitting out round 1.
    round2_match = MatchWithDetailsDefinitive(
        id=MatchId(-2),
        stage_item_input1=i1,
        stage_item_input2=i3,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-2),
        match_sets=_make_sets(MatchId(-2), [(5, 30)]),
    )

    stage_item = StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(-1),
                matches=[round1_match],
                stage_item_id=StageItemId(-1),
                created=now,
                lifecycle_state=RoundLifecycleState.LOCKED,
                name="",
            ),
            RoundWithMatches(
                id=RoundId(-2),
                matches=[round2_match],
                stage_item_id=StageItemId(-1),
                created=now,
                lifecycle_state=RoundLifecycleState.LOCKED,
                name="",
            ),
        ],
        inputs=[i1, i2, i3],
        type_name="Mexicano",
        team_count=3,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.MEXICANO,
    )

    result = determine_ranking_for_stage_item(
        stage_item, _ranking(tournament_id, now, win="3.0", draw="1.0")
    )
    # i3: round-1 bye compensation (15) + round-2 points scored (30) = 45.
    assert result[StageItemInputId(-3)].points == Decimal("45")


def test_mexicano_bye_compensation_ignores_incomplete_rounds() -> None:
    """A round with a not-yet-completed match contributes no compensation to its sitter."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    i1 = _mexicano_input(-1, 1, tournament_id)
    i2 = _mexicano_input(-2, 2, tournament_id)
    i3 = _mexicano_input(-3, 3, tournament_id)  # would sit out, round not complete yet

    in_progress_match = MatchWithDetails(
        id=MatchId(-1),
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=match_sets_for_state(MatchId(0), MatchState.IN_PROGRESS, 10, 5),
    )

    stage_item = StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(-1),
                matches=[in_progress_match],
                stage_item_id=StageItemId(-1),
                created=now,
                lifecycle_state=RoundLifecycleState.ACTIVE,
                name="",
            )
        ],
        inputs=[i1, i2, i3],
        type_name="Mexicano",
        team_count=3,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.MEXICANO,
    )

    result = determine_ranking_for_stage_item(
        stage_item, _ranking(tournament_id, now, win="3.0", draw="1.0")
    )
    assert result[StageItemInputId(-3)].points == Decimal("0")
