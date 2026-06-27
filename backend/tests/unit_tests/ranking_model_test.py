from decimal import Decimal

from heliclockter import datetime_utc

from bracket.logic.ranking.calculation import set_statistics_for_stage_item_input
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.match import MatchState, MatchWithDetailsDefinitive
from bracket.models.db.ranking import (
    Ranking,
    RankingMatchPointsData,
    ScoringType,
)
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


def test_scoring_type_values() -> None:
    assert ScoringType.MATCH_POINTS.value == "MATCH_POINTS"
    assert ScoringType.SET_POINTS.value == "SET_POINTS"
    assert ScoringType.SET_POINTS_WITH_MATCH_BONUS.value == "SET_POINTS_WITH_MATCH_BONUS"


def test_ranking_match_points_data_defaults() -> None:
    data = RankingMatchPointsData(
        win_points=Decimal("1.0"),
        draw_points=Decimal("0.5"),
        loss_points=Decimal("0.0"),
    )
    assert data.win_points == Decimal("1.0")
    assert data.draw_points == Decimal("0.5")
    assert data.loss_points == Decimal("0.0")


def _make_ranking_match_points(
    tournament_id: TournamentId,
    now: datetime_utc,
    win: str = "1.0",
    draw: str = "0.5",
    loss: str = "0.0",
) -> Ranking:
    return Ranking(
        id=RankingId(-1),
        tournament_id=tournament_id,
        created=now,
        position=0,
        scoring_type=ScoringType.MATCH_POINTS,
        match_points=RankingMatchPointsData(
            win_points=Decimal(win),
            draw_points=Decimal(draw),
            loss_points=Decimal(loss),
        ),
    )


def test_set_statistics_reads_from_match_points() -> None:
    """Calculation reads win/draw/loss from ranking.match_points, not flat fields."""
    from collections import defaultdict

    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    inp1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    inp2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )
    match = MatchWithDetailsDefinitive(
        id=MatchId(-1),
        stage_item_input1=inp1,
        stage_item_input2=inp2,
        created=now,
        duration_minutes=90,
        round_id=RoundId(-1),
        match_sets=match_sets_for_state(MatchId(0), MatchState.COMPLETED, 2, 0),
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
        inputs=[inp1, inp2],
        type_name="Round Robin",
        team_count=2,
        ranking_id=None,
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="",
        created=now,
        type=StageType.ROUND_ROBIN,
    )
    ranking = _make_ranking_match_points(tournament_id, now, win="3.0", draw="1.0", loss="0.0")
    stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(TeamStatistics)
    set_statistics_for_stage_item_input(0, stats, match, StageItemInputId(-1), ranking, stage_item)
    assert stats[StageItemInputId(-1)].wins == 1
    assert stats[StageItemInputId(-1)].points == Decimal("3.0")


def test_schema_rankings_has_new_columns() -> None:
    from bracket.schema import rankings

    cols = set(rankings.c.keys())
    assert "scoring_type" in cols
    assert "num_sets" in cols
    assert "max_points" in cols
    assert "last_set_max_points" in cols
    assert "two_point_advantage" in cols
    assert "win_points" not in cols
    assert "draw_points" not in cols
    assert "loss_points" not in cols
    assert "add_score_points" not in cols


def test_schema_rankings_has_name_column() -> None:
    from bracket.schema import rankings

    assert "name" in rankings.c.keys()


def test_migration_add_ranking_name_exists_and_chains_from_head() -> None:
    import importlib.util
    from pathlib import Path

    versions_dir = Path(__file__).parent.parent.parent / "alembic" / "versions"
    files = list(versions_dir.glob("*add_name_to_rankings*.py"))
    assert files, "No add_name_to_rankings migration file found"
    path = files[0]
    spec = importlib.util.spec_from_file_location("migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "b9d3e7f1a2c4"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_schema_subtype_tables_exist() -> None:
    from bracket.schema import (
        ranking_match_points,
        ranking_set_points,
        ranking_set_points_with_match_bonus,
    )

    assert "ranking_id" in ranking_match_points.c
    assert "win_points" in ranking_match_points.c
    assert "draw_points" in ranking_match_points.c
    assert "loss_points" in ranking_match_points.c

    assert "ranking_id" in ranking_set_points.c

    assert "ranking_id" in ranking_set_points_with_match_bonus.c
    assert "match_bonus_points" in ranking_set_points_with_match_bonus.c


def test_migration_redesign_exists_and_chains_from_side_switch() -> None:
    import importlib.util
    from pathlib import Path

    versions_dir = Path(__file__).parent.parent.parent / "alembic" / "versions"
    files = list(versions_dir.glob("*ranking_model_redesign*.py"))
    assert files, "No ranking_model_redesign migration file found"
    path = files[0]
    spec = importlib.util.spec_from_file_location("migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "d3b8f1c4e2a9"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_ranking_has_name_field() -> None:
    now = datetime_utc.now()
    ranking = Ranking(
        id=RankingId(1),
        tournament_id=TournamentId(1),
        created=now,
        position=0,
        name="Main ranking",
        scoring_type=ScoringType.MATCH_POINTS,
    )
    assert ranking.name == "Main ranking"


def test_ranking_name_defaults_to_empty_string() -> None:
    now = datetime_utc.now()
    ranking = Ranking(
        id=RankingId(1),
        tournament_id=TournamentId(1),
        created=now,
        position=0,
        scoring_type=ScoringType.MATCH_POINTS,
    )
    assert ranking.name == ""


def test_ranking_new_base_fields() -> None:
    now = datetime_utc.now()
    ranking = Ranking(
        id=RankingId(1),
        tournament_id=TournamentId(1),
        created=now,
        position=0,
        scoring_type=ScoringType.MATCH_POINTS,
        num_sets=1,
        max_points=21,
        last_set_max_points=None,
        two_point_advantage=True,
        match_points=RankingMatchPointsData(
            win_points=Decimal("1.0"),
            draw_points=Decimal("0.5"),
            loss_points=Decimal("0.0"),
        ),
    )
    assert ranking.scoring_type == ScoringType.MATCH_POINTS
    assert ranking.num_sets == 1
    assert ranking.max_points == 21
    assert ranking.two_point_advantage is True
    assert ranking.match_points is not None
    assert ranking.match_points.win_points == Decimal("1.0")
