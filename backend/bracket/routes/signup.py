from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from heliclockter import datetime_utc
from pydantic import Field, model_validator

from bracket.config import config
from bracket.database import database
from bracket.logic.subscriptions import subscription_lookup
from bracket.models.db.player import PlayerBody
from bracket.models.db.shared import BaseModelORM
from bracket.models.db.team import TeamInsertable
from bracket.models.db.tournament import Tournament
from bracket.routes.auth import tournament_by_signup_token
from bracket.routes.models import (
    SignupInfoResponse,
    SignupTeamInfo,
    SignupTournamentInfo,
    SuccessResponse,
)
from bracket.schema import players_x_teams, teams
from bracket.sql.players import get_all_players_in_tournament, insert_player
from bracket.sql.signup import (
    check_player_name_exists,
    count_players_on_team,
    get_signup_team_info_rows,
)
from bracket.sql.teams import get_team_by_id, get_teams_with_members
from bracket.sql.users import get_club_owner_user
from bracket.utils.id_types import TeamId
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)

_TEAM_NOT_FOUND = "Team not found"
_TEAM_CHOICE_DISABLED = "Team selection is not enabled for this signup"


class SignupBody(BaseModelORM):
    player_name: str = Field(..., min_length=1, max_length=30)
    team_action: Literal["join", "create", "none"]
    team_id: TeamId | None = None
    team_name: str | None = Field(None, max_length=30)

    @model_validator(mode="after")
    def validate_team_fields(self) -> "SignupBody":
        if self.team_action == "join" and self.team_id is None:
            raise ValueError("team_id is required when joining a team")
        if self.team_action == "create":
            name = (self.team_name or "").strip()
            if len(name) < 1:
                raise ValueError("team_name is required when creating a team")
            self.team_name = name
        return self


@router.get("/signup/{signup_token}", response_model=SignupInfoResponse)
async def get_signup_info(
    tournament: Tournament = Depends(tournament_by_signup_token),
) -> SignupInfoResponse:
    rows = await get_signup_team_info_rows(tournament.id)
    team_infos = [
        SignupTeamInfo(
            id=TeamId(r.id),
            name=r.name,
            player_count=r.player_count,
            is_full=r.player_count >= tournament.max_team_size,
        )
        for r in rows
    ]
    return SignupInfoResponse(
        data=SignupTournamentInfo(
            tournament_id=tournament.id,
            tournament_name=tournament.name,
            teams=team_infos,
            max_team_size=tournament.max_team_size,
            dashboard_endpoint=tournament.dashboard_endpoint,
            signup_team_choice_enabled=tournament.signup_team_choice_enabled,
        )
    )


@router.post("/signup/{signup_token}", response_model=SuccessResponse)
async def post_signup(
    body: SignupBody,
    tournament: Tournament = Depends(tournament_by_signup_token),
) -> SuccessResponse:
    if await check_player_name_exists(tournament.id, body.player_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A player with this name already exists",
        )

    if not tournament.signup_team_choice_enabled and body.team_action != "none":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_TEAM_CHOICE_DISABLED,
        )

    if body.team_action == "join":
        assert body.team_id is not None
        team = await get_team_by_id(body.team_id, tournament.id)
        if team is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_TEAM_NOT_FOUND,
            )
        on_team = await count_players_on_team(body.team_id, tournament.id)
        if on_team >= tournament.max_team_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This team is full",
            )

    owner = await get_club_owner_user(tournament.club_id)
    if owner is None:
        raise HTTPException(status_code=500, detail="Club owner not found")

    subscription = subscription_lookup[owner.account_type]
    existing_players = await get_all_players_in_tournament(tournament.id)
    if len(existing_players) + 1 > subscription.max_players:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tournament is full",
        )

    if body.team_action == "create":
        existing_teams = await get_teams_with_members(tournament.id)
        if len(existing_teams) + 1 > subscription.max_teams:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tournament is full",
            )

    async with database.transaction():
        player_id = await insert_player(
            PlayerBody(name=body.player_name, active=True), tournament.id
        )

        if body.team_action == "join":
            await database.execute(
                query=players_x_teams.insert(),
                values={"team_id": assert_some(body.team_id), "player_id": player_id},
            )

        elif body.team_action == "create":
            new_team_id = await database.execute(
                query=teams.insert(),
                values=TeamInsertable(
                    name=assert_some(body.team_name),
                    active=True,
                    created=datetime_utc.now(),
                    tournament_id=tournament.id,
                ).model_dump(),
            )
            await database.execute(
                query=players_x_teams.insert(),
                values={"team_id": new_team_id, "player_id": player_id},
            )

    return SuccessResponse()
