from bracket.database import database
from bracket.models.db.tournament import Tournament
from bracket.utils.id_types import TeamId, TournamentId


async def get_tournament_by_signup_token(signup_token: str) -> Tournament | None:
    """Fetch tournament where signup_token matches and signup is enabled."""
    query = """
        SELECT *
        FROM tournaments
        WHERE signup_token = :signup_token
        AND signup_enabled IS TRUE
        AND status = 'OPEN'
        """
    result = await database.fetch_one(query=query, values={"signup_token": signup_token})
    return Tournament.model_validate(result) if result is not None else None


async def get_tournament_by_score_tracking_token(score_tracking_token: str) -> Tournament | None:
    """Fetch tournament where score_tracking_token matches and score tracking is enabled."""
    query = """
        SELECT *
        FROM tournaments
        WHERE score_tracking_token = :score_tracking_token
        AND score_tracking_enabled IS TRUE
        AND status = 'OPEN'
        """
    result = await database.fetch_one(
        query=query, values={"score_tracking_token": score_tracking_token}
    )
    return Tournament.model_validate(result) if result is not None else None


async def check_player_name_exists(tournament_id: TournamentId, name: str) -> bool:
    """Case-insensitive check for duplicate player name in tournament."""
    query = """
        SELECT COUNT(*) AS cnt
        FROM players
        WHERE tournament_id = :tournament_id AND LOWER(name) = LOWER(:name)
        """
    row = await database.fetch_one(
        query=query, values={"tournament_id": tournament_id, "name": name}
    )
    assert row is not None
    return int(row["cnt"]) > 0


async def count_players_on_team(team_id: TeamId, tournament_id: TournamentId) -> int:
    query = """
        SELECT COUNT(*) AS cnt
        FROM players_x_teams pxt
        INNER JOIN teams t ON t.id = pxt.team_id
        WHERE pxt.team_id = :team_id AND t.tournament_id = :tournament_id
        """
    row = await database.fetch_one(
        query=query, values={"team_id": team_id, "tournament_id": tournament_id}
    )
    assert row is not None
    return int(row["cnt"])


class SignupTeamRow:
    __slots__ = ("id", "name", "player_count")

    def __init__(self, id_: int, name: str, player_count: int) -> None:
        self.id = id_
        self.name = name
        self.player_count = player_count


async def get_signup_team_info_rows(tournament_id: TournamentId) -> list[SignupTeamRow]:
    """Fetch teams with their player counts for the signup page."""
    query = """
        SELECT t.id, t.name, COUNT(pxt.player_id) AS player_count
        FROM teams t
        LEFT JOIN players_x_teams pxt ON pxt.team_id = t.id
        WHERE t.tournament_id = :tournament_id AND t.active = true
        GROUP BY t.id, t.name
        ORDER BY t.name
        """
    rows = await database.fetch_all(query=query, values={"tournament_id": tournament_id})
    return [
        SignupTeamRow(id_=r["id"], name=r["name"], player_count=int(r["player_count"]))
        for r in rows
    ]
