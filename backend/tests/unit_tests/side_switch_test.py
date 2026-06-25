from typing import Any

from bracket.models.db.ranking import RankingInsertable, RankingMatchPointsBody
from bracket.utils.id_types import TournamentId


def _base_insertable(**overrides: Any) -> RankingInsertable:
    return RankingInsertable(
        tournament_id=TournamentId(-1),
        position=0,
        **overrides,
    )


# ---------------------------------------------------------------------------
# Cycle 1 – Ranking model has side_switch_every_n_points
# ---------------------------------------------------------------------------


def test_ranking_insertable_accepts_side_switch_field() -> None:
    r = _base_insertable(side_switch_every_n_points=7)
    assert r.side_switch_every_n_points == 7


def test_ranking_insertable_side_switch_defaults_to_none() -> None:
    r = _base_insertable()
    assert r.side_switch_every_n_points is None


# ---------------------------------------------------------------------------
# Cycle 2 – RankingBody and RankingCreateBody expose side_switch_every_n_points
# ---------------------------------------------------------------------------


def test_ranking_body_accepts_side_switch_field() -> None:
    body = RankingMatchPointsBody(position=0, side_switch_every_n_points=7)
    assert body.side_switch_every_n_points == 7


def test_ranking_body_side_switch_defaults_to_none() -> None:
    body = RankingMatchPointsBody(position=0)
    assert body.side_switch_every_n_points is None


def test_ranking_create_body_side_switch_defaults_to_none() -> None:
    body = RankingMatchPointsBody()
    assert body.side_switch_every_n_points is None


# ---------------------------------------------------------------------------
# Cycle 3 – side switch trigger logic
# ---------------------------------------------------------------------------

from bracket.logic.ranking.side_switch import should_show_side_switch_reminder  # noqa: E402


def test_no_reminder_at_score_zero() -> None:
    assert should_show_side_switch_reminder(combined_score=0, n=7) is False


def test_reminder_at_threshold() -> None:
    assert should_show_side_switch_reminder(combined_score=7, n=7) is True


def test_no_reminder_between_thresholds() -> None:
    assert should_show_side_switch_reminder(combined_score=8, n=7) is False


def test_reminder_at_multiple_of_threshold() -> None:
    assert should_show_side_switch_reminder(combined_score=14, n=7) is True


def test_no_reminder_when_n_is_none() -> None:
    assert should_show_side_switch_reminder(combined_score=7, n=None) is False


# ---------------------------------------------------------------------------
# Cycle 5 – rankings table schema has side_switch_every_n_points column
# ---------------------------------------------------------------------------


def test_rankings_schema_has_side_switch_column() -> None:
    from bracket.schema import rankings

    assert "side_switch_every_n_points" in rankings.c


# ---------------------------------------------------------------------------
# Cycle 6 – Alembic migration is correctly chained and defines upgrade/downgrade
# ---------------------------------------------------------------------------


def test_migration_revision_and_chain() -> None:
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).parent.parent.parent
        / "alembic"
        / "versions"
        / "c2e4f9a1b7d3_add_side_switch_every_n_points_to_rankings.py"
    )
    spec = importlib.util.spec_from_file_location("migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "c2e4f9a1b7d3"
    assert migration.down_revision == "a2c4e6f8b1d3"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)
