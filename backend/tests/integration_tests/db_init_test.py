import pytest

from bracket.database import database
from bracket.models.db.match import MatchState
from bracket.models.db.stage_item import StageType
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.users import delete_user_and_owned_clubs
from bracket.utils.db_init import BIG_DEV_TOURNAMENT_NAME, sql_create_dev_db
from bracket.utils.id_types import LevelId, TournamentId


async def get_big_dev_tournament_id() -> TournamentId:
    result = await database.fetch_one(
        query="SELECT id FROM tournaments WHERE name = :name",
        values={"name": BIG_DEV_TOURNAMENT_NAME},
    )
    assert result is not None
    return TournamentId(result["id"])


async def get_level_ids_by_name(tournament_id: TournamentId) -> dict[str, LevelId]:
    rows = await database.fetch_all(
        query="""
            SELECT id, name
            FROM levels
            WHERE tournament_id = :tournament_id
            ORDER BY position
        """,
        values={"tournament_id": tournament_id},
    )
    return {row["name"]: LevelId(row["id"]) for row in rows}


async def get_team_counts_by_level(tournament_id: TournamentId) -> dict[str, int]:
    rows = await database.fetch_all(
        query="""
            SELECT levels.name, COUNT(teams.id) AS team_count
            FROM levels
            LEFT JOIN teams ON teams.level_id = levels.id
            WHERE levels.tournament_id = :tournament_id
            GROUP BY levels.id
            ORDER BY levels.position
        """,
        values={"tournament_id": tournament_id},
    )
    return {row["name"]: row["team_count"] for row in rows}


@pytest.mark.asyncio(loop_scope="session")
async def test_db_init() -> None:
    user_id = await sql_create_dev_db()
    try:
        tournament_id = await get_big_dev_tournament_id()
        level_ids_by_name = await get_level_ids_by_name(tournament_id)

        assert level_ids_by_name.keys() == {"Level A", "Level B", "Level C", "Level D"}
        assert await get_team_counts_by_level(tournament_id) == {
            "Level A": 5,
            "Level B": 12,
            "Level C": 14,
            "Level D": 4,
        }
        assert (
            await database.fetch_val(
                query="SELECT COUNT(*) FROM courts WHERE tournament_id = :tournament_id",
                values={"tournament_id": tournament_id},
            )
            == 10
        )

        stages = await get_full_tournament_details(tournament_id)
        stages_by_level = {
            level_name: [stage for stage in stages if stage.level_id == level_id]
            for level_name, level_id in level_ids_by_name.items()
        }

        level_a_group_stage = next(
            stage for stage in stages_by_level["Level A"] if stage.name == "Group Phase"
        )
        assert {
            (stage_item.name, stage_item.team_count, stage_item.type)
            for stage_item in level_a_group_stage.stage_items
        } == {
            ("Group A", 3, StageType.ROUND_ROBIN),
            ("Group B", 2, StageType.ROUND_ROBIN),
        }
        assert {stage.name for stage in stages_by_level["Level A"]} == {
            "Group Phase",
            "Semi-finals",
            "Finals",
        }

        for level_name, group_sizes in {
            "Level B": [3, 3, 3, 3],
            "Level C": [3, 3, 4, 4],
        }.items():
            assert {stage.name for stage in stages_by_level[level_name]} == {
                "Group Phase",
                "Semi-finals",
                "Finals",
            }
            group_stage = next(
                stage for stage in stages_by_level[level_name] if stage.name == "Group Phase"
            )
            assert sorted(item.team_count for item in group_stage.stage_items) == group_sizes

            semi_final_stage = next(
                stage for stage in stages_by_level[level_name] if stage.name == "Semi-finals"
            )
            assert {item.name for item in semi_final_stage.stage_items} == {
                "Semi-final A",
                "Semi-final B",
                "5th-8th Semi A",
                "5th-8th Semi B",
            }

            finals_stage = next(
                stage for stage in stages_by_level[level_name] if stage.name == "Finals"
            )
            assert {item.name for item in finals_stage.stage_items} == {
                "Final",
                "3rd Place",
                "5th Place",
                "7th Place",
            }

        level_d_stages = stages_by_level["Level D"]
        assert [stage.name for stage in level_d_stages] == ["Round Robin"]
        assert [
            (item.name, item.team_count, item.type) for item in level_d_stages[0].stage_items
        ] == [("Full Round Robin", 4, StageType.ROUND_ROBIN)]

        all_stage_items = [stage_item for stage in stages for stage_item in stage.stage_items]
        all_inputs = [input_ for stage_item in all_stage_items for input_ in stage_item.inputs]
        all_matches = [
            match
            for stage_item in all_stage_items
            for round_ in stage_item.rounds
            for match in round_.matches
        ]

        assert len(all_matches) == 60
        assert all(input_.points == 0 for input_ in all_inputs)
        assert all(input_.wins == 0 for input_ in all_inputs)
        assert all(input_.draws == 0 for input_ in all_inputs)
        assert all(input_.losses == 0 for input_ in all_inputs)
        assert all(match.state is MatchState.NOT_STARTED for match in all_matches)
        assert all(
            match_set.stage_item_input1_score == 0 and match_set.stage_item_input2_score == 0
            for match in all_matches
            for match_set in match.match_sets
        )
        assert all(len(match.match_sets) == 1 for match in all_matches)
        assert all(match.start_time is None for match in all_matches)
        assert all(match.court_id is None for match in all_matches)
    finally:
        await delete_user_and_owned_clubs(user_id)
