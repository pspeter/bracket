from heliclockter import datetime_utc

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import RefereeId, TeamId, TournamentId


class RefereeInsertable(BaseModelORM):
    tournament_id: TournamentId
    team_id: TeamId | None = None
    name: str | None = None
    created: datetime_utc


class Referee(RefereeInsertable):
    id: RefereeId
    # Read-only display helper populated when a referee is hydrated onto a match:
    # the name of the team this referee row points to (null for free-text referees).
    # It is never persisted; it has no column on the referees table.
    team_name: str | None = None
