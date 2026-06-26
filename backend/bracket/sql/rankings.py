from decimal import Decimal

from databases.interfaces import Record

from bracket.database import database
from bracket.models.db.ranking import (
    Ranking,
    RankingBody,
    RankingCreateBody,
    RankingMatchPointsBody,
    RankingMatchPointsData,
    RankingSetPointsWithMatchBonusBody,
    RankingSetPointsWithMatchBonusData,
    ScoringType,
)
from bracket.utils.id_types import LevelId, RankingId, StageId, StageItemId, TournamentId

# Common SELECT fragment that LEFT JOINs all three subtype tables
_RANKING_SELECT = """
    SELECT
        r.*,
        rmp.win_points   AS mp_win_points,
        rmp.draw_points  AS mp_draw_points,
        rmp.loss_points  AS mp_loss_points,
        rspwmb.match_bonus_points AS mp_match_bonus_points
    FROM rankings r
    LEFT JOIN ranking_match_points rmp ON rmp.ranking_id = r.id
    LEFT JOIN ranking_set_points_with_match_bonus rspwmb ON rspwmb.ranking_id = r.id
"""


def _row_to_ranking(row: Record) -> Ranking:
    m = dict(row._mapping)
    match_points = None
    if m.get("mp_win_points") is not None:
        match_points = RankingMatchPointsData(
            win_points=Decimal(str(m["mp_win_points"])),
            draw_points=Decimal(str(m["mp_draw_points"])),
            loss_points=Decimal(str(m["mp_loss_points"])),
        )
    set_points_with_bonus = None
    if m.get("mp_match_bonus_points") is not None:
        set_points_with_bonus = RankingSetPointsWithMatchBonusData(
            match_bonus_points=Decimal(str(m["mp_match_bonus_points"]))
        )
    return Ranking(
        id=m["id"],
        created=m["created"],
        tournament_id=m["tournament_id"],
        position=m["position"],
        scoring_type=ScoringType(m["scoring_type"]),
        num_sets=m["num_sets"],
        max_points=m["max_points"],
        last_set_max_points=m.get("last_set_max_points"),
        two_point_advantage=m["two_point_advantage"],
        level_id=m.get("level_id"),
        side_switch_every_n_points=m.get("side_switch_every_n_points"),
        match_points=match_points,
        set_points_with_bonus=set_points_with_bonus,
    )


async def get_all_rankings_in_tournament(tournament_id: TournamentId) -> list[Ranking]:
    query = _RANKING_SELECT + " WHERE r.tournament_id = :tournament_id ORDER BY r.position"
    rows = await database.fetch_all(query=query, values={"tournament_id": tournament_id})
    return [_row_to_ranking(row) for row in rows]


async def get_default_ranking_for_stage(tournament_id: TournamentId, stage_id: StageId) -> Ranking:
    query = (
        _RANKING_SELECT
        + """
        JOIN stages ON stages.id = :stage_id
        WHERE r.tournament_id = :tournament_id
          AND r.level_id IS NOT DISTINCT FROM stages.level_id
        ORDER BY r.position
        LIMIT 1
        """
    )
    result = await database.fetch_one(
        query=query, values={"tournament_id": tournament_id, "stage_id": stage_id}
    )
    assert result is not None, "No default ranking found for stage"
    return _row_to_ranking(result)


async def get_ranking_by_id(tournament_id: TournamentId, ranking_id: RankingId) -> Ranking | None:
    query = _RANKING_SELECT + " WHERE r.tournament_id = :tournament_id AND r.id = :ranking_id"
    result = await database.fetch_one(
        query=query, values={"tournament_id": tournament_id, "ranking_id": ranking_id}
    )
    return _row_to_ranking(result) if result else None


async def get_ranking_for_stage_item(
    tournament_id: TournamentId, stage_item_id: StageItemId
) -> Ranking | None:
    query = (
        _RANKING_SELECT
        + """
        JOIN stage_items si ON si.ranking_id = r.id
        WHERE r.tournament_id = :tournament_id
          AND si.id = :stage_item_id
        """
    )
    result = await database.fetch_one(
        query=query, values={"tournament_id": tournament_id, "stage_item_id": stage_item_id}
    )
    return _row_to_ranking(result) if result else None


async def _insert_subtype_row(ranking_id: int, body: RankingBody) -> None:
    if isinstance(body, RankingMatchPointsBody):
        await database.execute(
            query="""
                INSERT INTO ranking_match_points (ranking_id, win_points, draw_points, loss_points)
                VALUES (:ranking_id, :win_points, :draw_points, :loss_points)
            """,
            values={
                "ranking_id": ranking_id,
                "win_points": body.win_points,
                "draw_points": body.draw_points,
                "loss_points": body.loss_points,
            },
        )
    elif isinstance(body, RankingSetPointsWithMatchBonusBody):
        await database.execute(
            query="""
                INSERT INTO ranking_set_points_with_match_bonus (ranking_id, match_bonus_points)
                VALUES (:ranking_id, :match_bonus_points)
            """,
            values={
                "ranking_id": ranking_id,
                "match_bonus_points": body.match_bonus_points,
            },
        )
    else:
        # SET_POINTS — no extra columns
        await database.execute(
            query="INSERT INTO ranking_set_points (ranking_id) VALUES (:ranking_id)",
            values={"ranking_id": ranking_id},
        )


async def _delete_subtype_row(ranking_id: RankingId, scoring_type: ScoringType) -> None:
    table_map = {
        ScoringType.MATCH_POINTS: "ranking_match_points",
        ScoringType.SET_POINTS: "ranking_set_points",
        ScoringType.SET_POINTS_WITH_MATCH_BONUS: "ranking_set_points_with_match_bonus",
    }
    table = table_map[scoring_type]
    await database.execute(
        query=f"DELETE FROM {table} WHERE ranking_id = :ranking_id",
        values={"ranking_id": ranking_id},
    )


async def sql_update_ranking(
    tournament_id: TournamentId, ranking_id: RankingId, ranking_body: RankingBody
) -> None:
    # Fetch current scoring_type to detect type change
    current_row = await database.fetch_one(
        query=(
            "SELECT scoring_type FROM rankings"
            " WHERE id = :ranking_id AND tournament_id = :tournament_id"
        ),
        values={"ranking_id": ranking_id, "tournament_id": tournament_id},
    )
    assert current_row is not None, "Ranking not found"
    current_type = ScoringType(current_row._mapping["scoring_type"])

    await database.execute(
        query="""
            UPDATE rankings
            SET position = COALESCE(:position, position),
                scoring_type = :scoring_type,
                num_sets = :num_sets,
                max_points = :max_points,
                last_set_max_points = :last_set_max_points,
                two_point_advantage = :two_point_advantage,
                side_switch_every_n_points = :side_switch_every_n_points
            WHERE rankings.tournament_id = :tournament_id
            AND rankings.id = :ranking_id
        """,
        values={
            "ranking_id": ranking_id,
            "tournament_id": tournament_id,
            "position": ranking_body.position,
            "scoring_type": ranking_body.scoring_type,
            "num_sets": ranking_body.num_sets,
            "max_points": ranking_body.max_points,
            "last_set_max_points": ranking_body.last_set_max_points,
            "two_point_advantage": ranking_body.two_point_advantage,
            "side_switch_every_n_points": ranking_body.side_switch_every_n_points,
        },
    )

    if current_type != ScoringType(ranking_body.scoring_type):
        await _delete_subtype_row(ranking_id, current_type)
        await _insert_subtype_row(ranking_id, ranking_body)
    elif isinstance(ranking_body, RankingMatchPointsBody):
        await database.execute(
            query="""
                UPDATE ranking_match_points
                SET win_points = :win_points,
                    draw_points = :draw_points,
                    loss_points = :loss_points
                WHERE ranking_id = :ranking_id
            """,
            values={
                "ranking_id": ranking_id,
                "win_points": ranking_body.win_points,
                "draw_points": ranking_body.draw_points,
                "loss_points": ranking_body.loss_points,
            },
        )
    elif isinstance(ranking_body, RankingSetPointsWithMatchBonusBody):
        await database.execute(
            query="""
                UPDATE ranking_set_points_with_match_bonus
                SET match_bonus_points = :match_bonus_points
                WHERE ranking_id = :ranking_id
            """,
            values={
                "ranking_id": ranking_id,
                "match_bonus_points": ranking_body.match_bonus_points,
            },
        )


async def sql_delete_ranking(tournament_id: TournamentId, ranking_id: RankingId) -> None:
    query = "DELETE FROM rankings WHERE id = :ranking_id AND tournament_id = :tournament_id"
    await database.fetch_one(
        query=query, values={"ranking_id": ranking_id, "tournament_id": tournament_id}
    )


async def sql_create_ranking(
    tournament_id: TournamentId,
    ranking_body: RankingCreateBody,
    position: int,
    level_id: LevelId | None = None,
) -> None:
    ranking_id = await database.execute(
        query="""
            INSERT INTO rankings
            (tournament_id, position, scoring_type, num_sets, max_points,
             last_set_max_points, two_point_advantage, level_id, side_switch_every_n_points)
            VALUES (
                :tournament_id, :position, :scoring_type, :num_sets, :max_points,
                :last_set_max_points, :two_point_advantage, :level_id, :side_switch_every_n_points
            )
            RETURNING id
        """,
        values={
            "tournament_id": tournament_id,
            "position": position,
            "scoring_type": ranking_body.scoring_type,
            "num_sets": ranking_body.num_sets,
            "max_points": ranking_body.max_points,
            "last_set_max_points": ranking_body.last_set_max_points,
            "two_point_advantage": ranking_body.two_point_advantage,
            "level_id": level_id,
            "side_switch_every_n_points": ranking_body.side_switch_every_n_points,
        },
    )
    await _insert_subtype_row(ranking_id, ranking_body)
