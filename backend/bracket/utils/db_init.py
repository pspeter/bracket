import random
from typing import TYPE_CHECKING, Any

from heliclockter import datetime_utc
from pydantic import BaseModel

from bracket.config import Environment, config, environment
from bracket.database import database, engine
from bracket.logic.ranking.calculation import (
    recalculate_ranking_for_stage_item,
)
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.account import UserAccountType
from bracket.models.db.club import ClubInsertable
from bracket.models.db.court import CourtInsertable
from bracket.models.db.level import LevelInsertable
from bracket.models.db.match import Match, MatchBody, MatchState
from bracket.models.db.player import PlayerInsertable
from bracket.models.db.player_x_team import PlayerXTeamInsertable
from bracket.models.db.ranking import RankingInsertable
from bracket.models.db.round import RoundInsertable
from bracket.models.db.stage import StageInsertable
from bracket.models.db.stage_item import (
    StageItemInsertable,
    StageItemWithInputsCreate,
)
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
)
from bracket.models.db.team import TeamInsertable
from bracket.models.db.tournament import Tournament, TournamentInsertable
from bracket.models.db.user import UserInsertable
from bracket.models.db.user_x_club import UserXClubInsertable, UserXClubRelation
from bracket.schema import (
    clubs,
    courts,
    levels,
    matches,
    metadata,
    players,
    players_x_teams,
    rankings,
    rounds,
    stage_items,
    stages,
    teams,
    tournaments,
    users,
    users_x_clubs,
)
from bracket.sql.matches import sql_update_match
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.sql.users import create_user, get_user
from bracket.utils.alembic import alembic_stamp_head
from bracket.utils.db import insert_generic
from bracket.utils.dummy_records import (
    DUMMY_CLUB,
    DUMMY_COURT1,
    DUMMY_COURT2,
    DUMMY_LEVEL1,
    DUMMY_LEVEL2,
    DUMMY_MOCK_TIME,
    DUMMY_PLAYER1,
    DUMMY_PLAYER2,
    DUMMY_PLAYER3,
    DUMMY_PLAYER4,
    DUMMY_PLAYER5,
    DUMMY_PLAYER6,
    DUMMY_PLAYER7,
    DUMMY_PLAYER8,
    DUMMY_PLAYER_X_TEAM,
    DUMMY_RANKING1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM2,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
    DUMMY_TEAM4,
    DUMMY_TOURNAMENT,
    DUMMY_USER,
)
from bracket.utils.id_types import (
    ClubId,
    LevelId,
    PlayerId,
    StageId,
    TeamId,
    TournamentId,
    UserId,
)
from bracket.utils.logging import logger
from bracket.utils.security import hash_password
from bracket.utils.types import assert_some

if TYPE_CHECKING:
    from sqlalchemy import Table


async def create_admin_user() -> UserId:
    assert config.admin_email
    assert config.admin_password

    user = await create_user(
        UserInsertable(
            name="Admin",
            email=config.admin_email,
            password_hash=hash_password(config.admin_password),
            created=datetime_utc.now(),
            account_type=UserAccountType.REGULAR,
        )
    )
    return user.id


async def init_db_when_empty() -> UserId | None:
    table_count = await database.fetch_val(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
    )
    if config.admin_email and config.admin_password:
        if (table_count <= 1 and environment != Environment.CI) or (
            environment is Environment.DEVELOPMENT and await get_user(config.admin_email) is None
        ):
            logger.warning("Empty db detected, creating tables...")
            metadata.create_all(engine)
            alembic_stamp_head()

            logger.warning("Empty db detected, creating admin user...")
            return await create_admin_user()

    return None


async def apply_match_states(tournament_id: TournamentId, tournament_details: Tournament) -> None:
    all_matches: list[Any] = []
    for stage in await get_full_tournament_details(tournament_id):
        for stage_item in stage.stage_items:
            for round_ in stage_item.rounds:
                all_matches.extend(round_.matches)

    total = len(all_matches)
    completed_count = total // 3
    in_progress_count = max(1, total // 8)

    for i, match in enumerate(all_matches):
        if i < completed_count:
            state = MatchState.COMPLETED
            score1, score2 = random.randint(1, 10), random.randint(0, 9)
            completed_at: datetime_utc | None = DUMMY_MOCK_TIME
        elif i < completed_count + in_progress_count:
            state = MatchState.IN_PROGRESS
            score1, score2 = random.randint(0, 7), random.randint(0, 7)
            completed_at = None
        else:
            state = MatchState.NOT_STARTED
            score1, score2 = 0, 0
            completed_at = None

        await sql_update_match(
            match_id=assert_some(match.id),
            match=MatchBody.model_validate(
                {
                    **match.model_dump(),
                    "stage_item_input1_score": score1,
                    "stage_item_input2_score": score2,
                    "state": state,
                    "completed_at": completed_at,
                }
            ),
            tournament=tournament_details,
        )


async def sql_create_dev_db() -> UserId:
    # TODO: refactor into smaller functions
    # pylint: disable=too-many-statements
    assert environment is not Environment.PRODUCTION

    logger.warning("Initializing database with dummy records")
    await database.connect()
    metadata.drop_all(engine)
    metadata.create_all(engine)
    real_user_id = await init_db_when_empty()
    alembic_stamp_head()

    table_lookup: dict[type, Table] = {
        UserInsertable: users,
        ClubInsertable: clubs,
        StageInsertable: stages,
        TeamInsertable: teams,
        UserXClubInsertable: users_x_clubs,
        PlayerXTeamInsertable: players_x_teams,
        PlayerInsertable: players,
        RoundInsertable: rounds,
        Match: matches,
        TournamentInsertable: tournaments,
        CourtInsertable: courts,
        StageItemInsertable: stage_items,
        RankingInsertable: rankings,
        LevelInsertable: levels,
    }

    async def insert_dummy[BaseModelT: BaseModel](
        obj_to_insert: BaseModelT, update_data: dict[str, Any] = {}
    ) -> int:
        record_id, _ = await insert_generic(
            database,
            obj_to_insert.model_copy(update=update_data),
            table_lookup[type(obj_to_insert)],
            type(obj_to_insert),
        )
        return record_id

    user_id_1 = UserId(await insert_dummy(DUMMY_USER))
    club_id_1 = ClubId(await insert_dummy(DUMMY_CLUB))

    await insert_dummy(
        UserXClubInsertable(user_id=user_id_1, club_id=club_id_1, relation=UserXClubRelation.OWNER),
    )

    if real_user_id is not None:
        await insert_dummy(
            UserXClubInsertable(
                user_id=real_user_id, club_id=club_id_1, relation=UserXClubRelation.OWNER
            )
        )

    # --- Tournament 1: no levels ---
    tournament_id_1 = TournamentId(await insert_dummy(DUMMY_TOURNAMENT, {"club_id": club_id_1}))
    stage_id_1 = StageId(await insert_dummy(DUMMY_STAGE1, {"tournament_id": tournament_id_1}))
    stage_id_2 = StageId(await insert_dummy(DUMMY_STAGE2, {"tournament_id": tournament_id_1}))

    await insert_dummy(DUMMY_RANKING1, {"tournament_id": tournament_id_1})

    team_id_1 = TeamId(await insert_dummy(DUMMY_TEAM1, {"tournament_id": tournament_id_1}))
    team_id_2 = TeamId(await insert_dummy(DUMMY_TEAM2, {"tournament_id": tournament_id_1}))
    team_id_3 = TeamId(await insert_dummy(DUMMY_TEAM3, {"tournament_id": tournament_id_1}))
    team_id_4 = TeamId(await insert_dummy(DUMMY_TEAM4, {"tournament_id": tournament_id_1}))
    team_id_5 = TeamId(
        await insert_dummy(DUMMY_TEAM4, {"name": "Team 5", "tournament_id": tournament_id_1})
    )
    team_id_6 = TeamId(
        await insert_dummy(DUMMY_TEAM4, {"name": "Team 6", "tournament_id": tournament_id_1})
    )
    team_id_7 = TeamId(
        await insert_dummy(DUMMY_TEAM4, {"name": "Team 7", "tournament_id": tournament_id_1})
    )
    team_id_8 = TeamId(
        await insert_dummy(DUMMY_TEAM4, {"name": "Team 8", "tournament_id": tournament_id_1})
    )

    player_id_1 = PlayerId(await insert_dummy(DUMMY_PLAYER1, {"tournament_id": tournament_id_1}))
    player_id_2 = PlayerId(await insert_dummy(DUMMY_PLAYER2, {"tournament_id": tournament_id_1}))
    player_id_3 = PlayerId(await insert_dummy(DUMMY_PLAYER3, {"tournament_id": tournament_id_1}))
    player_id_4 = PlayerId(await insert_dummy(DUMMY_PLAYER4, {"tournament_id": tournament_id_1}))
    player_id_5 = PlayerId(await insert_dummy(DUMMY_PLAYER5, {"tournament_id": tournament_id_1}))
    player_id_6 = PlayerId(await insert_dummy(DUMMY_PLAYER6, {"tournament_id": tournament_id_1}))
    player_id_7 = PlayerId(await insert_dummy(DUMMY_PLAYER7, {"tournament_id": tournament_id_1}))
    player_id_8 = PlayerId(await insert_dummy(DUMMY_PLAYER8, {"tournament_id": tournament_id_1}))

    player_id_9 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 09", "tournament_id": tournament_id_1})
    )
    player_id_10 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 10", "tournament_id": tournament_id_1})
    )
    player_id_11 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 11", "tournament_id": tournament_id_1})
    )
    player_id_12 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 12", "tournament_id": tournament_id_1})
    )
    player_id_13 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 13", "tournament_id": tournament_id_1})
    )
    player_id_14 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 14", "tournament_id": tournament_id_1})
    )
    player_id_15 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 15", "tournament_id": tournament_id_1})
    )
    player_id_16 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 16", "tournament_id": tournament_id_1})
    )

    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_1, "team_id": team_id_1})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_2, "team_id": team_id_1})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_3, "team_id": team_id_2})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_4, "team_id": team_id_2})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_5, "team_id": team_id_3})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_6, "team_id": team_id_3})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_7, "team_id": team_id_4})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_8, "team_id": team_id_4})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_9, "team_id": team_id_5})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_10, "team_id": team_id_5})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_11, "team_id": team_id_6})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_12, "team_id": team_id_6})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_13, "team_id": team_id_7})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_14, "team_id": team_id_7})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_15, "team_id": team_id_8})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_16, "team_id": team_id_8})

    await insert_dummy(DUMMY_COURT1, {"tournament_id": tournament_id_1})
    await insert_dummy(DUMMY_COURT2, {"tournament_id": tournament_id_1})

    stage_item_1 = await sql_create_stage_item_with_inputs(
        tournament_id_1,
        StageItemWithInputsCreate(
            stage_id=stage_id_1,
            name=DUMMY_STAGE_ITEM1.name,
            team_count=DUMMY_STAGE_ITEM1.team_count,
            type=DUMMY_STAGE_ITEM1.type,
            inputs=[
                StageItemInputCreateBodyFinal(slot=1, team_id=team_id_1),
                StageItemInputCreateBodyFinal(slot=2, team_id=team_id_2),
                StageItemInputCreateBodyFinal(slot=3, team_id=team_id_3),
                StageItemInputCreateBodyFinal(slot=4, team_id=team_id_4),
            ],
        ),
    )
    stage_item_2 = await sql_create_stage_item_with_inputs(
        tournament_id_1,
        StageItemWithInputsCreate(
            stage_id=stage_id_1,
            name=DUMMY_STAGE_ITEM2.name,
            team_count=DUMMY_STAGE_ITEM2.team_count,
            type=DUMMY_STAGE_ITEM2.type,
            inputs=[
                StageItemInputCreateBodyFinal(slot=1, team_id=team_id_5),
                StageItemInputCreateBodyFinal(slot=2, team_id=team_id_6),
                StageItemInputCreateBodyFinal(slot=3, team_id=team_id_7),
                StageItemInputCreateBodyFinal(slot=4, team_id=team_id_8),
            ],
        ),
    )
    stage_item_3 = await sql_create_stage_item_with_inputs(
        tournament_id_1,
        StageItemWithInputsCreate(
            stage_id=stage_id_2,
            name=DUMMY_STAGE_ITEM3.name,
            team_count=DUMMY_STAGE_ITEM3.team_count,
            type=DUMMY_STAGE_ITEM3.type,
            inputs=[
                StageItemInputCreateBodyTentative(
                    slot=1,
                    winner_from_stage_item_id=stage_item_1.id,
                    winner_position=1,
                ),
                StageItemInputCreateBodyTentative(
                    slot=2,
                    winner_from_stage_item_id=stage_item_1.id,
                    winner_position=2,
                ),
                StageItemInputCreateBodyTentative(
                    slot=3,
                    winner_from_stage_item_id=stage_item_2.id,
                    winner_position=1,
                ),
                StageItemInputCreateBodyTentative(
                    slot=4,
                    winner_from_stage_item_id=stage_item_2.id,
                    winner_position=2,
                ),
            ],
        ),
    )

    await build_matches_for_stage_item(stage_item_1, tournament_id_1)
    await build_matches_for_stage_item(stage_item_2, tournament_id_1)
    await build_matches_for_stage_item(stage_item_3, tournament_id_1)

    tournament_details_1 = await sql_get_tournament(tournament_id_1)
    await apply_match_states(tournament_id_1, tournament_details_1)

    for _stage_item in (stage_item_1, stage_item_2, stage_item_3):
        stage_item_with_rounds = await get_stage_item(tournament_id_1, _stage_item.id)
        await recalculate_ranking_for_stage_item(tournament_id_1, stage_item_with_rounds)

    # --- Tournament 2: two levels (Beginners + Advanced) ---
    tournament_id_2 = TournamentId(
        await insert_dummy(
            DUMMY_TOURNAMENT,
            {
                "club_id": club_id_1,
                "name": "Leveled Tournament",
                "dashboard_endpoint": "levels-endpoint",
            },
        )
    )

    level_id_beginner = LevelId(
        await insert_dummy(DUMMY_LEVEL1, {"tournament_id": tournament_id_2})
    )
    level_id_advanced = LevelId(
        await insert_dummy(DUMMY_LEVEL2, {"tournament_id": tournament_id_2})
    )

    await insert_dummy(
        DUMMY_RANKING1,
        {"tournament_id": tournament_id_2, "level_id": level_id_beginner, "position": 0},
    )
    await insert_dummy(
        DUMMY_RANKING1,
        {"tournament_id": tournament_id_2, "level_id": level_id_advanced, "position": 1},
    )

    b_team_id_1 = TeamId(
        await insert_dummy(
            DUMMY_TEAM1,
            {"name": "B Team 1", "tournament_id": tournament_id_2, "level_id": level_id_beginner},
        )
    )
    b_team_id_2 = TeamId(
        await insert_dummy(
            DUMMY_TEAM2,
            {"name": "B Team 2", "tournament_id": tournament_id_2, "level_id": level_id_beginner},
        )
    )
    b_team_id_3 = TeamId(
        await insert_dummy(
            DUMMY_TEAM3,
            {"name": "B Team 3", "tournament_id": tournament_id_2, "level_id": level_id_beginner},
        )
    )
    b_team_id_4 = TeamId(
        await insert_dummy(
            DUMMY_TEAM4,
            {"name": "B Team 4", "tournament_id": tournament_id_2, "level_id": level_id_beginner},
        )
    )

    a_team_id_1 = TeamId(
        await insert_dummy(
            DUMMY_TEAM1,
            {"name": "A Team 1", "tournament_id": tournament_id_2, "level_id": level_id_advanced},
        )
    )
    a_team_id_2 = TeamId(
        await insert_dummy(
            DUMMY_TEAM2,
            {"name": "A Team 2", "tournament_id": tournament_id_2, "level_id": level_id_advanced},
        )
    )
    a_team_id_3 = TeamId(
        await insert_dummy(
            DUMMY_TEAM3,
            {"name": "A Team 3", "tournament_id": tournament_id_2, "level_id": level_id_advanced},
        )
    )
    a_team_id_4 = TeamId(
        await insert_dummy(
            DUMMY_TEAM4,
            {"name": "A Team 4", "tournament_id": tournament_id_2, "level_id": level_id_advanced},
        )
    )

    b_player_ids: list[PlayerId] = []
    for i in range(1, 9):
        b_player_ids.append(
            PlayerId(
                await insert_dummy(
                    DUMMY_PLAYER8,
                    {"name": f"B Player {i:02d}", "tournament_id": tournament_id_2},
                )
            )
        )

    a_player_ids: list[PlayerId] = []
    for i in range(1, 9):
        a_player_ids.append(
            PlayerId(
                await insert_dummy(
                    DUMMY_PLAYER8,
                    {"name": f"A Player {i:02d}", "tournament_id": tournament_id_2},
                )
            )
        )

    b_teams = [b_team_id_1, b_team_id_2, b_team_id_3, b_team_id_4]
    for i, b_player_id in enumerate(b_player_ids):
        await insert_dummy(
            DUMMY_PLAYER_X_TEAM, {"player_id": b_player_id, "team_id": b_teams[i // 2]}
        )

    a_teams = [a_team_id_1, a_team_id_2, a_team_id_3, a_team_id_4]
    for i, a_player_id in enumerate(a_player_ids):
        await insert_dummy(
            DUMMY_PLAYER_X_TEAM, {"player_id": a_player_id, "team_id": a_teams[i // 2]}
        )

    await insert_dummy(DUMMY_COURT1, {"tournament_id": tournament_id_2})
    await insert_dummy(DUMMY_COURT2, {"tournament_id": tournament_id_2})

    b_stage_id = StageId(
        await insert_dummy(
            DUMMY_STAGE1,
            {"tournament_id": tournament_id_2, "level_id": level_id_beginner},
        )
    )
    a_stage_id = StageId(
        await insert_dummy(
            DUMMY_STAGE1,
            {"tournament_id": tournament_id_2, "level_id": level_id_advanced},
        )
    )

    b_stage_item = await sql_create_stage_item_with_inputs(
        tournament_id_2,
        StageItemWithInputsCreate(
            stage_id=b_stage_id,
            name="Beginner Group",
            team_count=4,
            type=DUMMY_STAGE_ITEM1.type,
            inputs=[
                StageItemInputCreateBodyFinal(slot=1, team_id=b_team_id_1),
                StageItemInputCreateBodyFinal(slot=2, team_id=b_team_id_2),
                StageItemInputCreateBodyFinal(slot=3, team_id=b_team_id_3),
                StageItemInputCreateBodyFinal(slot=4, team_id=b_team_id_4),
            ],
        ),
    )
    a_stage_item = await sql_create_stage_item_with_inputs(
        tournament_id_2,
        StageItemWithInputsCreate(
            stage_id=a_stage_id,
            name="Advanced Group",
            team_count=4,
            type=DUMMY_STAGE_ITEM1.type,
            inputs=[
                StageItemInputCreateBodyFinal(slot=1, team_id=a_team_id_1),
                StageItemInputCreateBodyFinal(slot=2, team_id=a_team_id_2),
                StageItemInputCreateBodyFinal(slot=3, team_id=a_team_id_3),
                StageItemInputCreateBodyFinal(slot=4, team_id=a_team_id_4),
            ],
        ),
    )

    await build_matches_for_stage_item(b_stage_item, tournament_id_2)
    await build_matches_for_stage_item(a_stage_item, tournament_id_2)

    tournament_details_2 = await sql_get_tournament(tournament_id_2)
    await apply_match_states(tournament_id_2, tournament_details_2)

    for _stage_item in (b_stage_item, a_stage_item):
        stage_item_with_rounds = await get_stage_item(tournament_id_2, _stage_item.id)
        await recalculate_ranking_for_stage_item(tournament_id_2, stage_item_with_rounds)

    return user_id_1
