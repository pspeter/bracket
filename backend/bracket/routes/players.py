from fastapi import APIRouter, Depends, HTTPException, status

from bracket.config import config
from bracket.database import database
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.player import Player, PlayerBody, PlayerMultiBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import user_authenticated_for_tournament
from bracket.routes.models import (
    PaginatedPlayers,
    PlayersResponse,
    SinglePlayerResponse,
    SuccessResponse,
)
from bracket.routes.util import disallow_archived_tournament
from bracket.schema import players
from bracket.sql.players import (
    get_all_players_in_tournament,
    get_player_count,
    insert_player,
    player_name_exists,
    sql_delete_player,
)
from bracket.utils.db import fetch_one_parsed
from bracket.utils.id_types import PlayerId, TournamentId
from bracket.utils.pagination import PaginationPlayers
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)

_PLAYER_NAME_ALREADY_EXISTS = "A player with this name already exists"


@router.get("/tournaments/{tournament_id}/players", response_model=PlayersResponse)
async def get_players(
    tournament_id: TournamentId,
    not_in_team: bool = False,
    pagination: PaginationPlayers = Depends(),
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> PlayersResponse:
    return PlayersResponse(
        data=PaginatedPlayers(
            players=await get_all_players_in_tournament(
                tournament_id, not_in_team=not_in_team, pagination=pagination
            ),
            count=await get_player_count(tournament_id, not_in_team=not_in_team),
        )
    )


@router.put("/tournaments/{tournament_id}/players/{player_id}", response_model=SinglePlayerResponse)
async def update_player_by_id(
    tournament_id: TournamentId,
    player_id: PlayerId,
    player_body: PlayerBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SinglePlayerResponse:
    if await player_name_exists(tournament_id, player_body.name, except_player_id=player_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_PLAYER_NAME_ALREADY_EXISTS,
        )

    await database.execute(
        query=players.update().where(
            (players.c.id == player_id) & (players.c.tournament_id == tournament_id)
        ),
        values=player_body.model_dump(),
    )
    return SinglePlayerResponse(
        data=assert_some(
            await fetch_one_parsed(
                database,
                Player,
                players.select().where(
                    (players.c.id == player_id) & (players.c.tournament_id == tournament_id)
                ),
            )
        )
    )


@router.delete("/tournaments/{tournament_id}/players/{player_id}", response_model=SuccessResponse)
async def delete_player(
    tournament_id: TournamentId,
    player_id: PlayerId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    await sql_delete_player(tournament_id, player_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/players", response_model=SuccessResponse)
async def create_single_player(
    player_body: PlayerBody,
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    existing_players = await get_all_players_in_tournament(tournament_id)
    check_requirement(existing_players, user, "max_players")

    if await player_name_exists(tournament_id, player_body.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_PLAYER_NAME_ALREADY_EXISTS,
        )

    await insert_player(player_body, tournament_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/players_multi", response_model=SuccessResponse)
async def create_multiple_players(
    player_body: PlayerMultiBody,
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    player_names = [player.strip() for player in player_body.names.split("\n") if len(player) > 0]
    existing_players = await get_all_players_in_tournament(tournament_id)
    check_requirement(existing_players, user, "max_players", additions=len(player_names))

    seen_names_lower: set[str] = set()
    for player_name in player_names:
        if player_name.lower() in seen_names_lower:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A player with the name '{player_name}' already exists",
            )
        seen_names_lower.add(player_name.lower())

        if await player_name_exists(tournament_id, player_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A player with the name '{player_name}' already exists",
            )

    for player_name in player_names:
        await insert_player(PlayerBody(name=player_name, active=player_body.active), tournament_id)

    return SuccessResponse()
