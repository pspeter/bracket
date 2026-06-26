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
                            match_sets=match_sets_for_state(MatchId(0), MatchState.COMPLETED, 2, 0),
                        ),
                        MatchWithDetailsDefinitive(
                            id=MatchId(-2),
                            stage_item_input1=stage_item_input1,
                            stage_item_input2=stage_item_input2,
                            created=now,
                            duration_minutes=90,
                            round_id=RoundId(-1),
                            match_sets=match_sets_for_state(MatchId(0), MatchState.COMPLETED, 2, 2),
                        ),
                        MatchWithDetails(  # This gets ignored in ranking calculation
                            id=MatchId(-3),
                            created=now,
                            duration_minutes=90,
                            round_id=RoundId(-1),
                            match_sets=match_sets_for_state(
                                MatchId(0), MatchState.IN_PROGRESS, 3, 2
                            ),
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
        -2: TeamStatistics(
            wins=0,
            draws=1,
            losses=1,
            points=Decimal("1.25"),
            set_difference=-1,
            point_difference=-2,
        ),
        -1: TeamStatistics(
            wins=1, draws=1, losses=0, points=Decimal("4.75"), set_difference=1, point_difference=2
        ),
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
                            match_sets=match_sets_for_state(MatchId(0), MatchState.COMPLETED, 2, 0),
                        ),
                        MatchWithDetailsDefinitive(
                            id=MatchId(-2),
                            stage_item_input1=stage_item_input1,
                            stage_item_input2=stage_item_input2,
                            created=now,
                            duration_minutes=90,
                            round_id=RoundId(-1),
                            match_sets=match_sets_for_state(MatchId(0), MatchState.COMPLETED, 2, 2),
                        ),
                        MatchWithDetails(  # This gets ignored in ranking calculation
                            id=MatchId(-3),
                            created=now,
                            duration_minutes=90,
                            round_id=RoundId(-1),
                            match_sets=match_sets_for_state(
                                MatchId(0), MatchState.IN_PROGRESS, 3, 2
                            ),
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
        -2: TeamStatistics(
            wins=0,
            draws=1,
            losses=1,
            points=Decimal("1208"),
            set_difference=-1,
            point_difference=-2,
        ),
        -1: TeamStatistics(
            wins=1, draws=1, losses=0, points=Decimal("1320"), set_difference=1, point_difference=2
        ),
    }


def test_team_statistics_has_set_and_point_difference() -> None:
    stats = TeamStatistics()
    assert stats.set_difference == 0
    assert stats.point_difference == 0


def test_match_points_sort_by_set_difference_tiebreaker() -> None:
    """Teams tied on match points are ordered by set_difference (higher = better rank)."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    ranking = _ranking(tournament_id, now, win="1.0", draw="0.5")

    # match 1: team1 beats team2 in 2 sets (team1 set_diff +2, team2 -2)
    # match 2: team2 beats team1 in 3 sets - 2 wins to 1 (team2 set_diff +1, team1 -1)
    # team1 net set_diff: +2 - 1 = +1, points = 1 (1 win, 1 loss)
    # team2 net set_diff: -2 + 1 = -1, points = 1 (1 win, 1 loss)
    # team1 should rank above team2 due to better set_difference
    input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=2,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )

    from bracket.logic.ranking.calculation import determine_team_ranking_for_stage_item
    from bracket.models.db.match import MatchSet, MatchSetState

    def make_sets(match_id: MatchId, scores: list[tuple[int, int]]) -> list[MatchSet]:
        from bracket.utils.id_types import MatchSetId

        return [
            MatchSet(
                id=MatchSetId(match_id * 10 + i),
                match_id=match_id,
                set_number=i + 1,
                stage_item_input1_score=s1,
                stage_item_input2_score=s2,
                state=MatchSetState.COMPLETED,
            )
            for i, (s1, s2) in enumerate(scores)
        ]

    stage_item = StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(-1),
                matches=[
                    MatchWithDetailsDefinitive(
                        id=MatchId(-1),
                        stage_item_input1=input1,
                        stage_item_input2=input2,
                        created=now,
                        duration_minutes=90,
                        round_id=RoundId(-1),
                        match_sets=make_sets(MatchId(-1), [(21, 5), (21, 5)]),  # team1 wins 2-0
                    ),
                    MatchWithDetailsDefinitive(
                        id=MatchId(-2),
                        stage_item_input1=input2,
                        stage_item_input2=input1,
                        created=now,
                        duration_minutes=90,
                        round_id=RoundId(-1),
                        match_sets=make_sets(
                            MatchId(-2), [(21, 5), (5, 21), (21, 5)]
                        ),  # team2 wins 2-1
                    ),
                ],
                stage_item_id=StageItemId(-1),
                created=now,
                lifecycle_state=RoundLifecycleState.ACTIVE,
                name="",
            )
        ],
        inputs=[input1, input2],
        type_name="Round Robin",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.ROUND_ROBIN,
    )

    ranked = determine_team_ranking_for_stage_item(stage_item, ranking)
    # Both teams have 1 win (1 point each)
    assert ranked[0][0] == StageItemInputId(-1), "team1 should rank first (set_diff +2 vs 0)"
    assert ranked[1][0] == StageItemInputId(-2)


def _set_points_ranking(tournament_id: TournamentId, now: datetime_utc) -> Ranking:

    return Ranking(
        id=RankingId(-1),
        tournament_id=tournament_id,
        created=now,
        position=0,
        scoring_type=ScoringType.SET_POINTS,
        match_points=None,
        set_points_with_bonus=None,
    )


def _set_points_with_bonus_ranking(
    tournament_id: TournamentId, now: datetime_utc, bonus: str = "1.0"
) -> Ranking:
    from bracket.models.db.ranking import RankingSetPointsWithMatchBonusData

    return Ranking(
        id=RankingId(-1),
        tournament_id=tournament_id,
        created=now,
        position=0,
        scoring_type=ScoringType.SET_POINTS_WITH_MATCH_BONUS,
        match_points=None,
        set_points_with_bonus=RankingSetPointsWithMatchBonusData(match_bonus_points=Decimal(bonus)),
    )


def _make_stage_item(
    tournament_id: TournamentId,
    now: datetime_utc,
    input1: StageItemInputFinal,
    input2: StageItemInputFinal,
    matches: list[MatchWithDetailsDefinitive],
) -> StageItemWithRounds:
    return StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(-1),
                matches=matches,
                stage_item_id=StageItemId(-1),
                created=now,
                lifecycle_state=RoundLifecycleState.ACTIVE,
                name="",
            )
        ],
        inputs=[input1, input2],
        type_name="Round Robin",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.ROUND_ROBIN,
    )


def test_set_points_scoring_awards_one_point_per_set_won() -> None:
    """SET_POINTS: stats.points equals the number of sets won across all matches."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=2,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )
    ranking = _set_points_ranking(tournament_id, now)

    from bracket.models.db.match import MatchSet, MatchSetState
    from bracket.utils.id_types import MatchSetId

    # Match: team1 wins 3-1 (4 sets total)
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=[
            MatchSet(
                id=MatchSetId(1),
                match_id=MatchId(-1),
                set_number=1,
                stage_item_input1_score=21,
                stage_item_input2_score=10,
                state=MatchSetState.COMPLETED,
            ),
            MatchSet(
                id=MatchSetId(2),
                match_id=MatchId(-1),
                set_number=2,
                stage_item_input1_score=10,
                stage_item_input2_score=21,
                state=MatchSetState.COMPLETED,
            ),
            MatchSet(
                id=MatchSetId(3),
                match_id=MatchId(-1),
                set_number=3,
                stage_item_input1_score=21,
                stage_item_input2_score=10,
                state=MatchSetState.COMPLETED,
            ),
            MatchSet(
                id=MatchSetId(4),
                match_id=MatchId(-1),
                set_number=4,
                stage_item_input1_score=21,
                stage_item_input2_score=10,
                state=MatchSetState.COMPLETED,
            ),
        ],
    )

    result = determine_ranking_for_stage_item(
        _make_stage_item(tournament_id, now, input1, input2, [match]), ranking
    )
    assert result[StageItemInputId(-1)].points == Decimal("3")  # 3 sets won
    assert result[StageItemInputId(-2)].points == Decimal("1")  # 1 set won
    assert result[StageItemInputId(-1)].wins == 1
    assert result[StageItemInputId(-2)].losses == 1


def test_set_points_with_match_bonus_awards_bonus_for_win() -> None:
    """SET_POINTS_WITH_MATCH_BONUS: winner gets sets_won + match_bonus; draw gets sets_won only."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=2,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )
    ranking = _set_points_with_bonus_ranking(tournament_id, now, bonus="2.0")

    from bracket.models.db.match import MatchSet, MatchSetState
    from bracket.utils.id_types import MatchSetId

    # Match: team1 wins 2-1; bonus=2 → team1 gets 2(sets)+2(bonus)=4, team2 gets 1(set)
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=[
            MatchSet(
                id=MatchSetId(1),
                match_id=MatchId(-1),
                set_number=1,
                stage_item_input1_score=21,
                stage_item_input2_score=10,
                state=MatchSetState.COMPLETED,
            ),
            MatchSet(
                id=MatchSetId(2),
                match_id=MatchId(-1),
                set_number=2,
                stage_item_input1_score=10,
                stage_item_input2_score=21,
                state=MatchSetState.COMPLETED,
            ),
            MatchSet(
                id=MatchSetId(3),
                match_id=MatchId(-1),
                set_number=3,
                stage_item_input1_score=21,
                stage_item_input2_score=10,
                state=MatchSetState.COMPLETED,
            ),
        ],
    )

    result = determine_ranking_for_stage_item(
        _make_stage_item(tournament_id, now, input1, input2, [match]), ranking
    )
    assert result[StageItemInputId(-1)].points == Decimal("4")  # 2 sets won + 2 bonus
    assert result[StageItemInputId(-2)].points == Decimal("1")  # 1 set won, no bonus
    assert result[StageItemInputId(-1)].wins == 1
    assert result[StageItemInputId(-2)].losses == 1


def test_set_points_with_match_bonus_draw_gives_no_bonus() -> None:
    """SET_POINTS_WITH_MATCH_BONUS: draws give 1 point per set each, no match bonus."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=2,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )
    ranking = _set_points_with_bonus_ranking(tournament_id, now, bonus="3.0")

    from bracket.models.db.match import MatchSet, MatchSetState
    from bracket.utils.id_types import MatchSetId

    # num_sets=2 match, 1-1 draw: each team wins 1 set, no match bonus
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=[
            MatchSet(
                id=MatchSetId(1),
                match_id=MatchId(-1),
                set_number=1,
                stage_item_input1_score=21,
                stage_item_input2_score=10,
                state=MatchSetState.COMPLETED,
            ),
            MatchSet(
                id=MatchSetId(2),
                match_id=MatchId(-1),
                set_number=2,
                stage_item_input1_score=10,
                stage_item_input2_score=21,
                state=MatchSetState.COMPLETED,
            ),
        ],
    )

    result = determine_ranking_for_stage_item(
        _make_stage_item(tournament_id, now, input1, input2, [match]), ranking
    )
    assert result[StageItemInputId(-1)].points == Decimal("1")  # 1 set won, no bonus
    assert result[StageItemInputId(-2)].points == Decimal("1")  # 1 set won, no bonus
    assert result[StageItemInputId(-1)].draws == 1
    assert result[StageItemInputId(-2)].draws == 1


def test_match_points_sort_by_point_difference_when_set_difference_tied() -> None:
    """When points and set_difference are equal, point_difference breaks the tie."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    ranking = _ranking(tournament_id, now, win="1.0", draw="0.5")

    # Both teams: 1 win, 1 loss → 1 point each
    # Both teams: win one set, lose one set → set_diff = 0 for both
    # team1 wins the set 21-5, team2 wins the set 21-19 → point_diff team1 = (21-5)+(5-21)=0
    # Wait, that's symmetric. Let me try:
    # Match 1 (team1 vs team2): team1 wins 1 set 21-5, team2 wins 1 set 21-19 → draw? No, wait...
    # For a 1-set match: team1 wins with 21-5, so sets1=1, sets2=0 → team1 wins.
    # Let's do this: 2-set match format (num_sets=2 is unusual but valid)
    # Match 1: team1 wins set1 (21-5), team2 wins set2 (21-19). Draw (sets_won: 1-1).
    # Match 2 (reversed): team2 wins set1 (21-15), team1 wins set2 (21-5). Draw (1-1).
    # But then both have 0 wins, 2 draws → same points.
    # team1 point_diff: (21-5)+(19-21)+(15-21)+(21-5) = 16-2-6+16 = 24?
    # Actually let me think of a cleaner scenario with SINGLE-set matches:
    # Match 1: team1 wins single set 21-5 (sets won: team1=1, team2=0) → team1 wins match
    # Match 2: team2 wins single set 21-15 (sets won: team2=1, team1=0) → team2 wins match
    # Both have 1 win, 1 loss → equal points (1.0 each)
    # Both have set_diff: team1 = +1-1 = 0, team2 = -1+1 = 0
    # point_diff: team1 = (21-5)+(15-21) = 16-6 = +10, team2 = (5-21)+(21-15) = -16+6 = -10
    # team1 should rank first due to better point_difference

    from bracket.models.db.match import MatchSet, MatchSetState
    from bracket.utils.id_types import MatchSetId

    input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=2,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )

    match1 = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=[
            MatchSet(
                id=MatchSetId(1),
                match_id=MatchId(-1),
                set_number=1,
                stage_item_input1_score=21,
                stage_item_input2_score=5,
                state=MatchSetState.COMPLETED,
            )
        ],
    )
    match2 = MatchWithDetailsDefinitive(
        id=MatchId(-2),
        stage_item_input1=input2,
        stage_item_input2=input1,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=[
            MatchSet(
                id=MatchSetId(2),
                match_id=MatchId(-2),
                set_number=1,
                stage_item_input1_score=21,
                stage_item_input2_score=15,
                state=MatchSetState.COMPLETED,
            )
        ],
    )

    from bracket.logic.ranking.calculation import determine_team_ranking_for_stage_item

    ranked = determine_team_ranking_for_stage_item(
        _make_stage_item(tournament_id, now, input1, input2, [match1, match2]), ranking
    )
    assert ranked[0][0] == StageItemInputId(-1), "team1 should rank first (point_diff +10 vs -10)"
    assert ranked[1][0] == StageItemInputId(-2)


def test_set_points_draw_gives_one_point_per_set() -> None:
    """SET_POINTS: a 1-1 draw gives each team 1 point (their sets won)."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=2,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )
    ranking = _set_points_ranking(tournament_id, now)

    from bracket.models.db.match import MatchSet, MatchSetState
    from bracket.utils.id_types import MatchSetId

    # 2-set match ending 1-1 draw
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=[
            MatchSet(
                id=MatchSetId(1),
                match_id=MatchId(-1),
                set_number=1,
                stage_item_input1_score=21,
                stage_item_input2_score=10,
                state=MatchSetState.COMPLETED,
            ),
            MatchSet(
                id=MatchSetId(2),
                match_id=MatchId(-1),
                set_number=2,
                stage_item_input1_score=10,
                stage_item_input2_score=21,
                state=MatchSetState.COMPLETED,
            ),
        ],
    )
    result = determine_ranking_for_stage_item(
        _make_stage_item(tournament_id, now, input1, input2, [match]), ranking
    )
    assert result[StageItemInputId(-1)].points == Decimal("1")
    assert result[StageItemInputId(-2)].points == Decimal("1")
    assert result[StageItemInputId(-1)].draws == 1
    assert result[StageItemInputId(-2)].draws == 1


def test_match_points_draw_gives_draw_points() -> None:
    """MATCH_POINTS: a draw gives each team draw_points."""
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=2,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )
    ranking = _ranking(tournament_id, now, win="3.0", draw="1.0")

    from bracket.models.db.match import MatchSet, MatchSetState
    from bracket.utils.id_types import MatchSetId

    # 2-set match ending 1-1 draw
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=[
            MatchSet(
                id=MatchSetId(1),
                match_id=MatchId(-1),
                set_number=1,
                stage_item_input1_score=21,
                stage_item_input2_score=10,
                state=MatchSetState.COMPLETED,
            ),
            MatchSet(
                id=MatchSetId(2),
                match_id=MatchId(-1),
                set_number=2,
                stage_item_input1_score=10,
                stage_item_input2_score=21,
                state=MatchSetState.COMPLETED,
            ),
        ],
    )
    result = determine_ranking_for_stage_item(
        _make_stage_item(tournament_id, now, input1, input2, [match]), ranking
    )
    assert result[StageItemInputId(-1)].points == Decimal("1.0")  # draw_points
    assert result[StageItemInputId(-2)].points == Decimal("1.0")  # draw_points
    assert result[StageItemInputId(-1)].draws == 1


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
