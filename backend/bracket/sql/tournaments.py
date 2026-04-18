from typing import Any, Literal

from bracket.database import database
from bracket.models.db.tournament import (
    Tournament,
    TournamentBody,
    TournamentChangeStatusBody,
    TournamentUpdateBody,
)
from bracket.utils.id_types import TournamentId


async def sql_get_tournament(tournament_id: TournamentId) -> Tournament:
    query = """
        SELECT *
        FROM tournaments
        WHERE id = :tournament_id
        """
    result = await database.fetch_one(query=query, values={"tournament_id": tournament_id})
    assert result is not None
    return Tournament.model_validate(result)


async def sql_get_tournament_by_endpoint_name(endpoint_name: str) -> Tournament | None:
    query = """
        SELECT *
        FROM tournaments
        WHERE dashboard_endpoint = :endpoint_name
        AND dashboard_public IS TRUE
        """
    result = await database.fetch_one(query=query, values={"endpoint_name": endpoint_name})
    return Tournament.model_validate(result) if result is not None else None


async def sql_get_tournaments(
    club_ids: tuple[int, ...],
    endpoint_name: str | None = None,
    filter_: Literal["ALL", "OPEN", "ARCHIVED"] = "ALL",
) -> list[Tournament]:
    query = """
        SELECT *
        FROM tournaments
        WHERE club_id = any(:club_ids)
        """

    params: dict[str, Any] = {"club_ids": club_ids}

    if endpoint_name is not None:
        query += "AND dashboard_endpoint = :endpoint_name"
        params = {**params, "endpoint_name": endpoint_name}

    if filter_ == "OPEN":
        query += "AND status = 'OPEN'"
    elif filter_ == "ARCHIVED":
        query += "AND status = 'ARCHIVED'"

    result = await database.fetch_all(query=query, values=params)
    return [Tournament.model_validate(x) for x in result]


async def sql_delete_tournament(tournament_id: TournamentId) -> None:
    query = """
        DELETE FROM tournaments
        WHERE id = :tournament_id
        """
    await database.fetch_one(query=query, values={"tournament_id": tournament_id})


async def sql_update_tournament(
    tournament_id: TournamentId,
    tournament: TournamentUpdateBody,
    signup_token_update: str | None = None,
) -> None:
    values = {"tournament_id": tournament_id, **tournament.model_dump()}
    token_clause = ""
    if signup_token_update is not None:
        token_clause = ", signup_token = :signup_token"
        values["signup_token"] = signup_token_update

    query = f"""
        UPDATE tournaments
        SET
            start_time = :start_time,
            name = :name,
            dashboard_public = :dashboard_public,
            dashboard_endpoint = :dashboard_endpoint,
            players_can_be_in_multiple_teams = :players_can_be_in_multiple_teams,
            auto_assign_courts = :auto_assign_courts,
            duration_minutes = :duration_minutes,
            margin_minutes = :margin_minutes,
            signup_enabled = :signup_enabled,
            max_team_size = :max_team_size,
            signup_team_choice_enabled = :signup_team_choice_enabled
            {token_clause}
        WHERE tournaments.id = :tournament_id
        """
    await database.execute(query=query, values=values)


async def sql_update_tournament_status(
    tournament_id: TournamentId, body: TournamentChangeStatusBody
) -> None:
    query = """
        UPDATE tournaments
        SET
            status = :state,
            dashboard_public = :dashboard_public
        WHERE tournaments.id = :tournament_id
        """

    # Make dashboard non-public when archiving.
    # When tournament is archived, setting dashboard_public to False shouldn't have an effect.
    params = {"tournament_id": tournament_id, "state": body.status.value, "dashboard_public": False}
    await database.execute(query=query, values=params)


async def sql_create_tournament(tournament: TournamentBody) -> TournamentId:
    query = """
        INSERT INTO tournaments (
            name,
            start_time,
            club_id,
            dashboard_public,
            dashboard_endpoint,
            logo_path,
            players_can_be_in_multiple_teams,
            auto_assign_courts,
            duration_minutes,
            margin_minutes,
            signup_enabled,
            signup_token,
            max_team_size,
            signup_team_choice_enabled
        )
        VALUES (
            :name,
            :start_time,
            :club_id,
            :dashboard_public,
            :dashboard_endpoint,
            :logo_path,
            :players_can_be_in_multiple_teams,
            :auto_assign_courts,
            :duration_minutes,
            :margin_minutes,
            :signup_enabled,
            :signup_token,
            :max_team_size,
            :signup_team_choice_enabled
        )
        RETURNING id
        """
    values = dict(tournament.model_dump(exclude_none=False))
    values.setdefault("signup_token", None)
    new_id = await database.fetch_val(query=query, values=values)
    return TournamentId(new_id)
