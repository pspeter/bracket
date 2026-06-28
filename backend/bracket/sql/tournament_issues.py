from bracket.database import database
from bracket.models.db.tournament_issues import TournamentIssueEntry
from bracket.utils.id_types import TournamentId


async def _fetch_count(query: str, tournament_id: TournamentId) -> int:
    return int(await database.fetch_val(query=query, values={"tournament_id": tournament_id}))


def _entry(type_: str, count: int) -> list[TournamentIssueEntry]:
    if count == 0:
        return []
    return [TournamentIssueEntry(type=type_, count=count)]


async def get_tournament_issues(
    tournament_id: TournamentId,
) -> dict[str, list[TournamentIssueEntry]]:
    unplanned_matches = await _fetch_count(
        """
        SELECT count(*)
        FROM matches
        INNER JOIN rounds ON rounds.id = matches.round_id
        INNER JOIN stage_items ON stage_items.id = rounds.stage_item_id
        INNER JOIN stages ON stages.id = stage_items.stage_id
        WHERE stages.tournament_id = :tournament_id
        AND matches.start_time IS NULL
        """,
        tournament_id,
    )
    players_without_team = await _fetch_count(
        """
        SELECT count(*)
        FROM players
        WHERE players.tournament_id = :tournament_id
        AND NOT EXISTS (
            SELECT 1
            FROM players_x_teams pxt
            INNER JOIN teams ON teams.id = pxt.team_id
            WHERE pxt.player_id = players.id
            AND teams.tournament_id = :tournament_id
        )
        """,
        tournament_id,
    )
    empty_slots = await _fetch_count(
        """
        SELECT count(*)
        FROM stage_item_inputs
        WHERE stage_item_inputs.tournament_id = :tournament_id
        AND stage_item_inputs.team_id IS NULL
        AND stage_item_inputs.winner_from_stage_item_id IS NULL
        """,
        tournament_id,
    )
    unassigned_teams = await _fetch_count(
        """
        SELECT count(*)
        FROM teams
        WHERE teams.tournament_id = :tournament_id
        AND NOT EXISTS (
            SELECT 1
            FROM stage_item_inputs
            WHERE stage_item_inputs.tournament_id = :tournament_id
            AND stage_item_inputs.team_id = teams.id
        )
        """,
        tournament_id,
    )
    teams_below_min_size = await _fetch_count(
        """
        SELECT count(*)
        FROM (
            SELECT teams.id
            FROM teams
            INNER JOIN tournaments ON tournaments.id = teams.tournament_id
            LEFT JOIN players_x_teams ON players_x_teams.team_id = teams.id
            WHERE teams.tournament_id = :tournament_id
            GROUP BY teams.id, tournaments.min_team_size
            HAVING count(players_x_teams.player_id) < tournaments.min_team_size
        ) underfilled_teams
        """,
        tournament_id,
    )

    return {
        "planning": _entry("unplanned_matches", unplanned_matches),
        "players": _entry("players_without_team", players_without_team),
        "stages": [
            *_entry("empty_slots", empty_slots),
            *_entry("unassigned_teams", unassigned_teams),
        ],
        "teams": _entry("teams_below_min_size", teams_below_min_size),
    }
