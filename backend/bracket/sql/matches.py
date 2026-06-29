from datetime import datetime

from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.match_sets.pointer import (
    apply_end,
    apply_reopen,
    apply_reset,
    apply_start,
)
from bracket.models.db.match import Match, MatchBody, MatchCreateBody, MatchWithDetails
from bracket.models.db.tournament import Tournament
from bracket.sql.match_sets import MATCH_SETS_SUBQUERY, sql_create_match_sets
from bracket.utils.id_types import (
    CourtId,
    MatchId,
    RoundId,
    StageItemId,
    StageItemInputId,
    TournamentId,
)


async def sql_delete_match(match_id: MatchId) -> None:
    query = """
        DELETE FROM matches
        WHERE matches.id = :match_id
        """
    await database.execute(query=query, values={"match_id": match_id})


async def sql_delete_matches(match_ids: list[MatchId]) -> None:
    for match_id in match_ids:
        await sql_delete_match(match_id)


async def sql_delete_matches_for_stage_item_id(stage_item_id: StageItemId) -> None:
    query = """
        DELETE FROM matches
        WHERE matches.id IN (
            SELECT matches.id
            FROM matches
            LEFT JOIN rounds ON matches.round_id = rounds.id
            WHERE rounds.stage_item_id = :stage_item_id
        )
        """
    await database.execute(query=query, values={"stage_item_id": stage_item_id})


async def sql_get_num_sets_for_round(round_id: RoundId) -> int:
    """Return the number of sets configured by the ranking applicable to a round's stage item.

    Falls back to 1 when no ranking is found (mirrors the historical single-score behaviour).
    """
    query = """
        SELECT rankings.num_sets
        FROM rounds
        JOIN stage_items ON stage_items.id = rounds.stage_item_id
        JOIN rankings ON rankings.id = stage_items.ranking_id
        WHERE rounds.id = :round_id
        """
    result = await database.fetch_one(query=query, values={"round_id": round_id})
    if result is None:
        return 1
    return int(result._mapping["num_sets"])


async def sql_create_match(match: MatchCreateBody) -> Match:
    query = """
        INSERT INTO matches (
            round_id,
            court_id,
            stage_item_input1_id,
            stage_item_input2_id,
            stage_item_input1_winner_from_match_id,
            stage_item_input2_winner_from_match_id,
            duration_minutes,
            custom_duration_minutes,
            created,
            input1_slot,
            input2_slot,
            referee_slot
        )
        VALUES (
            :round_id,
            :court_id,
            :stage_item_input1_id,
            :stage_item_input2_id,
            :stage_item_input1_winner_from_match_id,
            :stage_item_input2_winner_from_match_id,
            :duration_minutes,
            :custom_duration_minutes,
            NOW(),
            :input1_slot,
            :input2_slot,
            :referee_slot
        )
        RETURNING *
    """
    # The match insert and its set pre-population must be atomic: a match with zero sets
    # derives as NOT_STARTED forever and renders no editable rows, so never leave one behind.
    async with database.transaction():
        result = await database.fetch_one(query=query, values=match.model_dump())

        if result is None:
            raise ValueError("Could not create stage")

        created_match = Match.model_validate(dict(result._mapping))

        # Pre-populate one row in match_sets per configured set, all NOT_STARTED at 0–0.
        num_sets = await sql_get_num_sets_for_round(created_match.round_id)
        await sql_create_match_sets(created_match.id, num_sets)

    return created_match


async def sql_update_match(match_id: MatchId, match: MatchBody, tournament: Tournament) -> None:
    query = """
        UPDATE matches
        SET round_id = :round_id,
            court_id = :court_id,
            custom_duration_minutes = :custom_duration_minutes,
            duration_minutes = :duration_minutes
        WHERE matches.id = :match_id
        RETURNING *
        """

    duration_minutes = (
        match.custom_duration_minutes
        if match.custom_duration_minutes is not None
        else tournament.duration_minutes
    )
    await database.execute(
        query=query,
        values={
            "match_id": match_id,
            "round_id": match.round_id,
            "court_id": match.court_id,
            "custom_duration_minutes": match.custom_duration_minutes,
            "duration_minutes": duration_minutes,
        },
    )


async def sql_set_match_completed_at(match_id: MatchId, completed_at: datetime_utc | None) -> None:
    await database.execute(
        query="UPDATE matches SET completed_at = :completed_at WHERE id = :match_id",
        values={
            "match_id": match_id,
            "completed_at": (
                datetime.fromisoformat(completed_at.isoformat())
                if completed_at is not None
                else None
            ),
        },
    )


async def sql_set_input_ids_for_match(
    round_id: RoundId, match_id: MatchId, input_ids: list[StageItemInputId | None]
) -> None:
    query = """
        UPDATE matches
        SET stage_item_input1_id = :input1_id,
            stage_item_input2_id = :input2_id
        WHERE round_id = :round_id
        AND matches.id = :match_id
        """
    await database.execute(
        query=query,
        values={
            "round_id": round_id,
            "match_id": match_id,
            "input1_id": input_ids[0],
            "input2_id": input_ids[1],
        },
    )


async def sql_reschedule_match(
    match_id: MatchId,
    court_id: CourtId | None,
    start_time: datetime_utc,
    duration_minutes: int,
    custom_duration_minutes: int | None,
) -> None:
    query = """
        UPDATE matches
        SET court_id = :court_id,
            start_time = :start_time,
            duration_minutes = :duration_minutes,
            custom_duration_minutes = :custom_duration_minutes
        WHERE matches.id = :match_id
        """
    await database.execute(
        query=query,
        values={
            "court_id": court_id,
            "match_id": match_id,
            "start_time": datetime.fromisoformat(start_time.isoformat()),
            "duration_minutes": duration_minutes,
            "custom_duration_minutes": custom_duration_minutes,
        },
    )


async def sql_reschedule_match_and_determine_duration(
    court_id: CourtId | None,
    start_time: datetime_utc,
    match: Match,
    tournament: Tournament,
) -> None:
    duration_minutes = (
        tournament.duration_minutes
        if match.custom_duration_minutes is None
        else match.custom_duration_minutes
    )
    await sql_reschedule_match(
        match.id,
        court_id,
        start_time,
        duration_minutes,
        match.custom_duration_minutes,
    )


async def sql_unschedule_match(match_id: MatchId) -> None:
    query = """
        UPDATE matches
        SET court_id = NULL,
            start_time = NULL
        WHERE matches.id = :match_id
        """
    await database.execute(query=query, values={"match_id": match_id})


async def sql_get_match(match_id: MatchId) -> Match:
    query = f"""
        SELECT
            matches.*,
            {MATCH_SETS_SUBQUERY}
        FROM matches
        WHERE matches.id = :match_id
        """
    result = await database.fetch_one(query=query, values={"match_id": match_id})

    if result is None:
        raise ValueError("Could not create stage")

    return Match.model_validate(dict(result._mapping))


async def sql_get_match_with_details(
    tournament_id: TournamentId, match_id: MatchId
) -> MatchWithDetails | None:
    query = f"""
        WITH inputs_with_teams AS (
            SELECT DISTINCT ON (stage_item_inputs.id)
                stage_item_inputs.*,
                to_json(t.*) AS team
            FROM stage_item_inputs
            JOIN stage_items on stage_item_inputs.stage_item_id = stage_items.id
            JOIN stages on stages.id = stage_items.stage_id
            LEFT JOIN teams t on t.id = stage_item_inputs.team_id
            WHERE stages.tournament_id = :tournament_id
            GROUP BY stage_item_inputs.id, t.id
        )
        SELECT DISTINCT ON (matches.id)
            matches.*,
            to_json(sii1) AS stage_item_input1,
            to_json(sii2) AS stage_item_input2,
            to_json(c) AS court,
            to_json(ref_sii) AS referee,
            stages.level_id AS level_id,
            rankings.side_switch_every_n_points AS side_switch_every_n_points,
            rankings.num_sets AS num_sets,
            rankings.max_points AS max_points,
            rankings.last_set_max_points AS last_set_max_points,
            rankings.two_point_advantage AS two_point_advantage,
            {MATCH_SETS_SUBQUERY}
        FROM matches
        JOIN rounds ON rounds.id = matches.round_id
        JOIN stage_items ON stage_items.id = rounds.stage_item_id
        JOIN stages ON stages.id = stage_items.stage_id
        JOIN rankings ON rankings.id = stage_items.ranking_id
        LEFT JOIN inputs_with_teams sii1 ON sii1.id = matches.stage_item_input1_id
        LEFT JOIN inputs_with_teams sii2 ON sii2.id = matches.stage_item_input2_id
        LEFT JOIN courts c ON c.id = matches.court_id
        LEFT JOIN inputs_with_teams ref_sii ON ref_sii.id = matches.referee_stage_item_input_id
        WHERE stages.tournament_id = :tournament_id
        AND matches.id = :match_id
        """
    result = await database.fetch_one(
        query=query, values={"tournament_id": tournament_id, "match_id": match_id}
    )
    return MatchWithDetails.model_validate(dict(result._mapping)) if result is not None else None


async def sql_get_scheduled_matches_with_details(
    tournament_id: TournamentId,
    court_id: CourtId | None = None,
) -> list[MatchWithDetails]:
    court_filter = "AND matches.court_id = :court_id" if court_id is not None else ""
    match_sets = MATCH_SETS_SUBQUERY
    query = f"""
        WITH inputs_with_teams AS (
            SELECT DISTINCT ON (stage_item_inputs.id)
                stage_item_inputs.*,
                to_json(t.*) AS team
            FROM stage_item_inputs
            JOIN stage_items on stage_item_inputs.stage_item_id = stage_items.id
            JOIN stages on stages.id = stage_items.stage_id
            LEFT JOIN teams t on t.id = stage_item_inputs.team_id
            WHERE stages.tournament_id = :tournament_id
            GROUP BY stage_item_inputs.id, t.id
        )
        SELECT DISTINCT ON (matches.id)
            matches.*,
            to_json(sii1) AS stage_item_input1,
            to_json(sii2) AS stage_item_input2,
            to_json(c) AS court,
            to_json(ref_sii) AS referee,
            stages.level_id AS level_id,
            rankings.side_switch_every_n_points AS side_switch_every_n_points,
            rankings.num_sets AS num_sets,
            rankings.max_points AS max_points,
            rankings.last_set_max_points AS last_set_max_points,
            rankings.two_point_advantage AS two_point_advantage,
            {match_sets}
        FROM matches
        JOIN rounds ON rounds.id = matches.round_id
        JOIN stage_items ON stage_items.id = rounds.stage_item_id
        JOIN stages ON stages.id = stage_items.stage_id
        JOIN rankings ON rankings.id = stage_items.ranking_id
        LEFT JOIN inputs_with_teams sii1 ON sii1.id = matches.stage_item_input1_id
        LEFT JOIN inputs_with_teams sii2 ON sii2.id = matches.stage_item_input2_id
        LEFT JOIN courts c ON c.id = matches.court_id
        LEFT JOIN inputs_with_teams ref_sii ON ref_sii.id = matches.referee_stage_item_input_id
        WHERE stages.tournament_id = :tournament_id
        AND matches.start_time IS NOT NULL
        {court_filter}
        ORDER BY matches.id, matches.start_time, c.name, matches.id
        """
    values: dict[str, object] = {"tournament_id": tournament_id}
    if court_id is not None:
        values["court_id"] = court_id
    result = await database.fetch_all(query=query, values=values)
    matches = [MatchWithDetails.model_validate(dict(row._mapping)) for row in result]
    return sorted(
        matches,
        key=lambda match: (
            match.start_time.isoformat() if match.start_time is not None else "",
            match.court.name if match.court is not None else "",
            match.id,
        ),
    )


async def _lock_match_pointer(match_id: MatchId) -> tuple[int, bool, int]:
    lock_row = await database.fetch_one(
        query="""
            SELECT
                m.completed_set_count,
                m.current_set_in_progress,
                (SELECT COUNT(*)::int FROM match_sets ms WHERE ms.match_id = m.id) AS num_sets
            FROM matches m
            WHERE m.id = :match_id
            FOR UPDATE OF m
        """,
        values={"match_id": match_id},
    )
    if lock_row is None:
        raise ValueError(f"Could not find match {match_id}")
    return (
        int(lock_row._mapping["completed_set_count"]),
        bool(lock_row._mapping["current_set_in_progress"]),
        int(lock_row._mapping["num_sets"]),
    )


async def _update_match_pointer(
    match_id: MatchId, completed_set_count: int, current_set_in_progress: bool
) -> None:
    await database.execute(
        query="""
            UPDATE matches
            SET completed_set_count = :completed_set_count,
                current_set_in_progress = :current_set_in_progress
            WHERE id = :match_id
        """,
        values={
            "match_id": match_id,
            "completed_set_count": completed_set_count,
            "current_set_in_progress": current_set_in_progress,
        },
    )


async def sql_start_match(match_id: MatchId) -> None:
    completed, in_progress, num_sets = await _lock_match_pointer(match_id)
    new_completed, new_in_progress = apply_start(completed, in_progress, num_sets)
    await _update_match_pointer(match_id, new_completed, new_in_progress)


async def sql_end_match(match_id: MatchId) -> None:
    completed, in_progress, _num_sets = await _lock_match_pointer(match_id)
    new_completed, new_in_progress = apply_end(completed, in_progress)
    await _update_match_pointer(match_id, new_completed, new_in_progress)


async def sql_reopen_match(match_id: MatchId) -> None:
    completed, in_progress, _num_sets = await _lock_match_pointer(match_id)
    new_completed, new_in_progress = apply_reopen(completed, in_progress)
    await _update_match_pointer(match_id, new_completed, new_in_progress)


async def sql_reset_match(match_id: MatchId) -> None:
    await _lock_match_pointer(match_id)
    await database.execute(
        query="""
            UPDATE match_sets
            SET stage_item_input1_score = 0,
                stage_item_input2_score = 0
            WHERE match_id = :match_id
        """,
        values={"match_id": match_id},
    )
    new_completed, new_in_progress = apply_reset()
    await _update_match_pointer(match_id, new_completed, new_in_progress)
