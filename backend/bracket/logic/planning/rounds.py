from heliclockter import datetime_utc, timedelta

from bracket.logic.planning.matches import get_scheduled_matches_per_court
from bracket.models.db.match import MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.utils.id_types import CourtId


class MatchTimingAdjustmentInfeasible(Exception):
    pass


def get_draft_round(
    stage_item: StageItemWithRounds,
) -> RoundWithMatches | None:
    return next(
        (round_ for round_ in sorted(stage_item.rounds, key=lambda r: r.id) if round_.is_draft),
        None,
    )


def get_all_scheduling_operations_for_swiss_round(
    court_ids: list[CourtId],
    stages: list[StageWithStageItems],
    tournament: Tournament,
    active_round_matches: list[MatchWithDetailsDefinitive | MatchWithDetails],
    adjust_to_time: datetime_utc | None = None,
) -> list[tuple[CourtId, datetime_utc, MatchWithDetailsDefinitive | MatchWithDetails, Tournament]]:
    matches_per_court = get_scheduled_matches_per_court(stages)
    rescheduling_operations = []

    if len(court_ids) < 1:
        return []

    assert len(active_round_matches) <= len(court_ids)

    for i, match in enumerate(active_round_matches):
        court_id = court_ids[i]
        last_match = (
            next((m for m in matches_per_court[court_id][::-1] if m.match.id != match.id), None)
            if court_id in matches_per_court
            else None
        )

        if last_match is not None:
            last_match_end = last_match.match.end_time
            if adjust_to_time is not None:
                if adjust_to_time < last_match_end:
                    raise MatchTimingAdjustmentInfeasible(
                        "A match from the previous round is still happening"
                    )
                start_time = adjust_to_time
            else:
                start_time = last_match_end + timedelta(minutes=tournament.margin_minutes)
        else:
            start_time = (
                max(tournament.start_time, adjust_to_time)
                if adjust_to_time is not None
                else tournament.start_time
            )

        rescheduling_operations.append((court_id, start_time, match, tournament))

    return rescheduling_operations
