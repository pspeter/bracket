from datetime import datetime

from heliclockter import datetime_utc

from bracket.database import database
from bracket.models.db.match import Match, MatchBody, MatchCreateBody, MatchState, MatchWithDetails
from bracket.models.db.tournament import Tournament
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
            margin_minutes,
            custom_margin_minutes,
            stage_item_input1_score,
            stage_item_input2_score,
            stage_item_input1_conflict,
            stage_item_input2_conflict,
            created,
            state
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
            :margin_minutes,
            :custom_margin_minutes,
            0,
            0,
            false,
            false,
            NOW(),
            'NOT_STARTED'
        )
        RETURNING *
    """
    result = await database.fetch_one(query=query, values=match.model_dump())

    if result is None:
        raise ValueError("Could not create stage")

    return Match.model_validate(dict(result._mapping))


async def sql_update_match(match_id: MatchId, match: MatchBody, tournament: Tournament) -> None:
    query = """
        UPDATE matches
        SET round_id = :round_id,
            stage_item_input1_score = :stage_item_input1_score,
            stage_item_input2_score = :stage_item_input2_score,
            court_id = :court_id,
            custom_duration_minutes = :custom_duration_minutes,
            custom_margin_minutes = :custom_margin_minutes,
            duration_minutes = :duration_minutes,
            margin_minutes = :margin_minutes,
            state = :state,
            completed_at = :completed_at
        WHERE matches.id = :match_id
        RETURNING *
        """

    duration_minutes = (
        match.custom_duration_minutes
        if match.custom_duration_minutes is not None
        else tournament.duration_minutes
    )
    margin_minutes = (
        match.custom_margin_minutes
        if match.custom_margin_minutes is not None
        else tournament.margin_minutes
    )
    await database.execute(
        query=query,
        values={
            "match_id": match_id,
            **match.model_dump(),
            "duration_minutes": duration_minutes,
            "margin_minutes": margin_minutes,
            "state": match.state.value,
            "completed_at": (
                datetime.fromisoformat(match.completed_at.isoformat())
                if getattr(match, "completed_at", None) is not None
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
    position_in_schedule: int | None,
    duration_minutes: int,
    margin_minutes: int,
    custom_duration_minutes: int | None,
    custom_margin_minutes: int | None,
    stage_item_input1_conflict: bool,
    stage_item_input2_conflict: bool,
) -> None:
    query = """
        UPDATE matches
        SET court_id = :court_id,
            start_time = :start_time,
            position_in_schedule = :position_in_schedule,
            duration_minutes = :duration_minutes,
            margin_minutes = :margin_minutes,
            custom_duration_minutes = :custom_duration_minutes,
            custom_margin_minutes = :custom_margin_minutes,
            stage_item_input1_conflict = :stage_item_input1_conflict,
            stage_item_input2_conflict = :stage_item_input2_conflict
        WHERE matches.id = :match_id
        """
    await database.execute(
        query=query,
        values={
            "court_id": court_id,
            "match_id": match_id,
            "position_in_schedule": position_in_schedule,
            "start_time": datetime.fromisoformat(start_time.isoformat()),
            "duration_minutes": duration_minutes,
            "margin_minutes": margin_minutes,
            "custom_duration_minutes": custom_duration_minutes,
            "custom_margin_minutes": custom_margin_minutes,
            "stage_item_input1_conflict": stage_item_input1_conflict,
            "stage_item_input2_conflict": stage_item_input2_conflict,
        },
    )


async def sql_reschedule_match_and_determine_duration_and_margin(
    court_id: CourtId | None,
    start_time: datetime_utc,
    position_in_schedule: int | None,
    match: Match,
    tournament: Tournament,
) -> None:
    duration_minutes = (
        tournament.duration_minutes
        if match.custom_duration_minutes is None
        else match.custom_duration_minutes
    )
    margin_minutes = (
        tournament.margin_minutes
        if match.custom_margin_minutes is None
        else match.custom_margin_minutes
    )
    await sql_reschedule_match(
        match.id,
        court_id,
        start_time,
        position_in_schedule,
        duration_minutes,
        margin_minutes,
        match.custom_duration_minutes,
        match.custom_margin_minutes,
        match.stage_item_input1_conflict,
        match.stage_item_input2_conflict,
    )


async def sql_unschedule_match(match_id: MatchId) -> None:
    query = """
        UPDATE matches
        SET court_id = NULL,
            start_time = NULL,
            position_in_schedule = NULL
        WHERE matches.id = :match_id
        """
    await database.execute(query=query, values={"match_id": match_id})


async def sql_get_match(match_id: MatchId) -> Match:
    query = """
        SELECT *
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
    query = """
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
            to_json(c) AS court
        FROM matches
        JOIN rounds ON rounds.id = matches.round_id
        JOIN stage_items ON stage_items.id = rounds.stage_item_id
        JOIN stages ON stages.id = stage_items.stage_id
        LEFT JOIN inputs_with_teams sii1 ON sii1.id = matches.stage_item_input1_id
        LEFT JOIN inputs_with_teams sii2 ON sii2.id = matches.stage_item_input2_id
        LEFT JOIN courts c ON c.id = matches.court_id
        WHERE stages.tournament_id = :tournament_id
        AND matches.id = :match_id
        """
    result = await database.fetch_one(
        query=query, values={"tournament_id": tournament_id, "match_id": match_id}
    )
    return MatchWithDetails.model_validate(dict(result._mapping)) if result is not None else None


async def sql_get_scheduled_matches_with_details(tournament_id: TournamentId) -> list[MatchWithDetails]:
    query = """
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
            to_json(c) AS court
        FROM matches
        JOIN rounds ON rounds.id = matches.round_id
        JOIN stage_items ON stage_items.id = rounds.stage_item_id
        JOIN stages ON stages.id = stage_items.stage_id
        LEFT JOIN inputs_with_teams sii1 ON sii1.id = matches.stage_item_input1_id
        LEFT JOIN inputs_with_teams sii2 ON sii2.id = matches.stage_item_input2_id
        LEFT JOIN courts c ON c.id = matches.court_id
        WHERE stages.tournament_id = :tournament_id
        AND rounds.is_draft IS FALSE
        AND matches.start_time IS NOT NULL
        ORDER BY matches.id, matches.start_time, c.name, matches.id
        """
    result = await database.fetch_all(query=query, values={"tournament_id": tournament_id})
    matches = [MatchWithDetails.model_validate(dict(row._mapping)) for row in result]
    return sorted(
        matches,
        key=lambda match: (
            match.start_time.isoformat() if match.start_time is not None else "",
            match.court.name if match.court is not None else "",
            match.id,
        ),
    )


async def clear_scores_for_matches_in_stage_item(
    tournament_id: TournamentId, stage_item_id: StageItemId
) -> None:
    query = """
        UPDATE matches
        SET stage_item_input1_score = 0,
            stage_item_input2_score = 0
        FROM rounds
        JOIN stage_items ON rounds.stage_item_id = stage_items.id
        JOIN stages ON stages.id = stage_items.stage_id
        WHERE   rounds.id = matches.round_id
            AND stages.tournament_id = :tournament_id
            AND stage_items.id = :stage_item_id
        """
    await database.execute(
        query=query,
        values={
            "stage_item_id": stage_item_id,
            "tournament_id": tournament_id,
        },
    )
