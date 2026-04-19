from pydantic import BaseModel

from bracket.logic.scheduling.handle_stage_activation import StageItemInputUpdate
from bracket.models.db.club import Club
from bracket.models.db.court import Court
from bracket.models.db.match import Match, MatchWithDetails, SuggestedMatch
from bracket.models.db.player import Player
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item_inputs import (
    StageItemInputOptionFinal,
    StageItemInputOptionTentative,
)
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import StageWithStageItems
from bracket.routes.auth import Token
from bracket.utils.id_types import StageId, StageItemId, TeamId, TournamentId


class SuccessResponse(BaseModel):
    success: bool = True


class DataResponse[DataT](BaseModel):
    data: DataT


class ClubsResponse(DataResponse[list[Club]]):
    pass


class ClubResponse(DataResponse[Club | None]):
    pass


class TournamentResponse(DataResponse[Tournament]):
    pass


class TournamentsResponse(DataResponse[list[Tournament]]):
    pass


class PaginatedPlayers(BaseModel):
    count: int
    players: list[Player]


class PlayersResponse(DataResponse[PaginatedPlayers]):
    pass


class SinglePlayerResponse(DataResponse[Player]):
    pass


class StagesWithStageItemsResponse(DataResponse[list[StageWithStageItems]]):
    pass


class UpcomingMatchesResponse(DataResponse[list[SuggestedMatch]]):
    pass


class SingleMatchResponse(DataResponse[Match]):
    pass


class PaginatedTeams(BaseModel):
    count: int
    teams: list[FullTeamWithPlayers]


class TeamsWithPlayersResponse(DataResponse[PaginatedTeams]):
    pass


class SingleTeamResponse(DataResponse[Team]):
    pass


class UserPublicResponse(DataResponse[UserPublic]):
    pass


class TokenResponse(DataResponse[Token]):
    pass


class CourtsResponse(DataResponse[list[Court]]):
    pass


class SingleCourtResponse(DataResponse[Court]):
    pass


class RankingsResponse(DataResponse[list[Ranking]]):
    pass


class StageItemInputOptionsResponse(
    DataResponse[dict[StageId, list[StageItemInputOptionTentative | StageItemInputOptionFinal]]]
):
    pass


class StageRankingResponse(DataResponse[dict[StageItemId, list[StageItemInputUpdate]]]):
    has_pending_matches: bool = False
    pending_match_count: int = 0
    pending_matches_message: str | None = None


class SignupTeamInfo(BaseModel):
    id: TeamId
    name: str
    player_count: int
    is_full: bool


class SignupTournamentInfo(BaseModel):
    tournament_id: TournamentId
    tournament_name: str
    teams: list[SignupTeamInfo]
    max_team_size: int
    dashboard_endpoint: str | None
    signup_team_choice_enabled: bool


class SignupInfoResponse(DataResponse[SignupTournamentInfo]):
    pass


class ScoreTrackingInfo(BaseModel):
    tournament_id: TournamentId
    tournament_name: str
    matches: list[MatchWithDetails]


class ScoreTrackingInfoResponse(DataResponse[ScoreTrackingInfo]):
    pass


class ScoreTrackingMatchResponse(DataResponse[MatchWithDetails]):
    pass
