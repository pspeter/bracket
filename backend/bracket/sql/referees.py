from bracket.database import database
from bracket.models.db.referee import Referee
from bracket.utils.id_types import MatchId, RefereeId, TeamId, TournamentId


async def sql_get_referees(tournament_id: TournamentId) -> list[Referee]:
    query = """
        SELECT *
        FROM referees
        WHERE tournament_id = :tournament_id
        ORDER BY referees.id
        """
    result = await database.fetch_all(query=query, values={"tournament_id": tournament_id})
    return [Referee.model_validate(dict(row._mapping)) for row in result]


async def sql_get_referee_by_id(
    tournament_id: TournamentId, referee_id: RefereeId
) -> Referee | None:
    query = """
        SELECT *
        FROM referees
        WHERE tournament_id = :tournament_id
        AND referees.id = :referee_id
        """
    result = await database.fetch_one(
        query=query, values={"tournament_id": tournament_id, "referee_id": referee_id}
    )
    return Referee.model_validate(dict(result._mapping)) if result is not None else None


async def sql_get_referee_by_team(tournament_id: TournamentId, team_id: TeamId) -> Referee | None:
    query = """
        SELECT *
        FROM referees
        WHERE tournament_id = :tournament_id
        AND team_id = :team_id
        """
    result = await database.fetch_one(
        query=query, values={"tournament_id": tournament_id, "team_id": team_id}
    )
    return Referee.model_validate(dict(result._mapping)) if result is not None else None


async def sql_upsert_referee_by_team(tournament_id: TournamentId, team_id: TeamId) -> Referee:
    """
    Return the tournament's referee row for this team, creating it if necessary.

    A team has at most one referee row per tournament, so this is idempotent: calling
    it again with the same team returns the same row instead of creating a duplicate.
    """
    existing = await sql_get_referee_by_team(tournament_id, team_id)
    if existing is not None:
        return existing

    query = """
        INSERT INTO referees (tournament_id, team_id, name, created)
        VALUES (:tournament_id, :team_id, NULL, NOW())
        RETURNING *
        """
    result = await database.fetch_one(
        query=query, values={"tournament_id": tournament_id, "team_id": team_id}
    )
    assert result is not None
    return Referee.model_validate(dict(result._mapping))


async def sql_set_match_referee(match_id: MatchId, referee_id: RefereeId | None) -> None:
    query = """
        UPDATE matches
        SET referee_id = :referee_id
        WHERE matches.id = :match_id
        """
    await database.execute(query=query, values={"match_id": match_id, "referee_id": referee_id})
