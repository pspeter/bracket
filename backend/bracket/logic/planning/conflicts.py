from collections import defaultdict
from dataclasses import dataclass

from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.planning.team_windows import PlayingWindow, get_team_playing_windows
from bracket.models.db.match import Match, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.util import StageWithStageItems
from bracket.utils.id_types import (
    CourtId,
    MatchId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


def matches_overlap(match1: Match, match2: Match) -> bool:
    if match1.start_time is None or match2.start_time is None:
        return False

    # Half-open intervals [start, end): back-to-back matches (end1 == start2) do not conflict.
    return _time_ranges_overlap(
        match1.start_time, match1.end_time, match2.start_time, match2.end_time
    )


def _time_ranges_overlap(
    start1: datetime_utc,
    end1: datetime_utc,
    start2: datetime_utc,
    end2: datetime_utc,
) -> bool:
    return start1 < end2 and start2 < end1


def _windows_overlap(window1: PlayingWindow, window2: PlayingWindow) -> bool:
    return _time_ranges_overlap(
        window1.start_time,
        window1.end_time,
        window2.start_time,
        window2.end_time,
    )


@dataclass
class MatchConflictFlags:
    stage_item_input1_conflict: bool = False
    stage_item_input2_conflict: bool = False
    precedence_conflict: bool = False
    short_break_conflict: bool = False
    referee_conflict: bool = False


def _get_all_matches(
    stages: list[StageWithStageItems],
) -> list[MatchWithDetailsDefinitive | MatchWithDetails]:
    return [
        match
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
    ]


def _set_team_overlap_conflicts(
    stages: list[StageWithStageItems],
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    for team_windows in get_team_playing_windows(stages).values():
        definitive_windows = [
            (match, window)
            for match, window in team_windows
            if isinstance(match, MatchWithDetailsDefinitive)
        ]
        for i, (match1, window1) in enumerate(definitive_windows):
            for match2, window2 in definitive_windows[i + 1 :]:
                if match1.id == match2.id or not _windows_overlap(window1, window2):
                    continue
                _set_stage_item_input_conflict(match1, window1, flags)
                _set_stage_item_input_conflict(match2, window2, flags)


def _set_stage_item_input_conflict(
    match: MatchWithDetailsDefinitive,
    window: PlayingWindow,
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    if window.stage_item_input_id == match.stage_item_input1_id:
        flags[match.id].stage_item_input1_conflict = True
        return
    if window.stage_item_input_id == match.stage_item_input2_id:
        flags[match.id].stage_item_input2_conflict = True
        return

    raise ValueError("Playing window input does not belong to match")


def _set_winner_of_precedence_conflicts(
    matches: list[MatchWithDetailsDefinitive | MatchWithDetails],
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    matches_by_id = {match.id: match for match in matches}

    for match in matches:
        if match.start_time is None:
            continue

        feeder_ids = [
            match.stage_item_input1_winner_from_match_id,
            match.stage_item_input2_winner_from_match_id,
        ]
        for feeder_id in feeder_ids:
            if feeder_id is None:
                continue
            feeder = matches_by_id.get(feeder_id)
            if (
                feeder is not None
                and feeder.start_time is not None
                and match.start_time < feeder.end_time
            ):
                flags[match.id].precedence_conflict = True


def _get_stage_item_end_times(
    stages: list[StageWithStageItems],
) -> dict[StageItemId, datetime_utc]:
    stage_item_end_times: dict[StageItemId, datetime_utc] = {}
    for stage in stages:
        for stage_item in stage.stage_items:
            latest_end_time: datetime_utc | None = None
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    if match.start_time is None:
                        continue
                    if latest_end_time is None or match.end_time > latest_end_time:
                        latest_end_time = match.end_time
            if latest_end_time is not None:
                stage_item_end_times[stage_item.id] = latest_end_time
    return stage_item_end_times


def _get_stage_item_start_times(
    stages: list[StageWithStageItems],
) -> dict[StageItemId, datetime_utc]:
    stage_item_start_times: dict[StageItemId, datetime_utc] = {}
    for stage in stages:
        for stage_item in stage.stage_items:
            earliest_start_time: datetime_utc | None = None
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    if match.start_time is None:
                        continue
                    if earliest_start_time is None or match.start_time < earliest_start_time:
                        earliest_start_time = match.start_time
            if earliest_start_time is not None:
                stage_item_start_times[stage_item.id] = earliest_start_time
    return stage_item_start_times


def _get_earliest_dependent_start_times(
    stages: list[StageWithStageItems],
) -> dict[StageItemId, datetime_utc]:
    """Map each source stage item to the earliest start of any stage item feeding off it.

    A stage item "feeds off" a source when one of its matches has an input whose
    ``winner_from_stage_item_id`` points at that source.
    """
    stage_item_start_times = _get_stage_item_start_times(stages)
    earliest_dependent_start: dict[StageItemId, datetime_utc] = {}

    for stage in stages:
        for stage_item in stage.stage_items:
            dependent_start = stage_item_start_times.get(stage_item.id)
            if dependent_start is None:
                continue
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    for stage_item_input in (match.stage_item_input1, match.stage_item_input2):
                        if (
                            stage_item_input is None
                            or stage_item_input.winner_from_stage_item_id is None
                        ):
                            continue
                        source_id = stage_item_input.winner_from_stage_item_id
                        existing = earliest_dependent_start.get(source_id)
                        if existing is None or dependent_start < existing:
                            earliest_dependent_start[source_id] = dependent_start

    return earliest_dependent_start


def _set_cross_stage_precedence_conflicts(
    stages: list[StageWithStageItems],
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    stage_item_end_times = _get_stage_item_end_times(stages)

    for match in _get_all_matches(stages):
        if match.start_time is None:
            continue

        for stage_item_input in (match.stage_item_input1, match.stage_item_input2):
            if stage_item_input is None or stage_item_input.winner_from_stage_item_id is None:
                continue
            source_end_time = stage_item_end_times.get(stage_item_input.winner_from_stage_item_id)
            if source_end_time is not None and match.start_time < source_end_time:
                flags[match.id].precedence_conflict = True


def _set_cross_stage_feeder_precedence_conflicts(
    stages: list[StageWithStageItems],
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    """Flag feeder matches scheduled after the stage item they feed into has started.

    The mirror image of ``_set_cross_stage_precedence_conflicts``: a source stage item must
    finish before any stage item consuming its ranking begins. Here we flag the *source* matches
    that are still running once a dependent stage item's earliest match has started, so the
    precedence conflict is marked on both sides of the dependency.
    """
    earliest_dependent_start = _get_earliest_dependent_start_times(stages)

    for stage in stages:
        for stage_item in stage.stage_items:
            dependent_start = earliest_dependent_start.get(stage_item.id)
            if dependent_start is None:
                continue
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    if match.start_time is None:
                        continue
                    if match.end_time > dependent_start:
                        flags[match.id].precedence_conflict = True


def _set_short_break_conflicts(
    matches: list[MatchWithDetailsDefinitive | MatchWithDetails],
    default_break_minutes: int,
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    matches_by_court: defaultdict[CourtId, list[MatchWithDetailsDefinitive | MatchWithDetails]] = (
        defaultdict(list)
    )
    for match in matches:
        if match.court_id is not None and match.start_time is not None:
            matches_by_court[match.court_id].append(match)

    for court_matches in matches_by_court.values():
        scheduled = sorted(court_matches, key=lambda match: (match.start_time, match.id))
        for previous, match in zip(scheduled, scheduled[1:], strict=False):
            assert previous.start_time is not None
            assert match.start_time is not None
            break_minutes = (match.start_time - previous.end_time).total_seconds() / 60
            if break_minutes < default_break_minutes:
                flags[match.id].short_break_conflict = True


def _set_referee_overlap_conflicts(
    stages: list[StageWithStageItems],
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    team_playing_windows = get_team_playing_windows(stages)
    refereeing_matches_by_team: defaultdict[
        TeamId, list[MatchWithDetailsDefinitive | MatchWithDetails]
    ] = defaultdict(list)

    for match in _get_all_matches(stages):
        if match.start_time is None:
            continue
        referee = match.referee
        if referee is None or referee.team_id is None:
            continue

        refereeing_matches_by_team[referee.team_id].append(match)

        for playing_match, playing_window in team_playing_windows.get(referee.team_id, []):
            if not _time_ranges_overlap(
                match.start_time,
                match.end_time,
                playing_window.start_time,
                playing_window.end_time,
            ):
                continue
            flags[match.id].referee_conflict = True
            if isinstance(playing_match, MatchWithDetailsDefinitive):
                _set_stage_item_input_conflict(playing_match, playing_window, flags)

    # A team cannot referee two matches that overlap in time; flag both of them.
    for refereeing_matches in refereeing_matches_by_team.values():
        for i, match1 in enumerate(refereeing_matches):
            for match2 in refereeing_matches[i + 1 :]:
                if matches_overlap(match1, match2):
                    flags[match1.id].referee_conflict = True
                    flags[match2.id].referee_conflict = True


@dataclass(frozen=True)
class _SlotOccupancy:
    """A match's use of a single stage_item_input slot, as either a player or the referee.

    ``playing_side`` is 1 or 2 for the two playing slots, or None when the match occupies the
    slot as its referee. This mirrors the auto-scheduler and the frontend placement preview,
    which treat the referee as a third match slot alongside the two playing slots.
    """

    match: MatchWithDetailsDefinitive | MatchWithDetails
    start_time: datetime_utc
    end_time: datetime_utc
    playing_side: int | None


def _flag_slot_occupancy(
    occupancy: _SlotOccupancy, flags: dict[MatchId, MatchConflictFlags]
) -> None:
    if occupancy.playing_side == 1:
        flags[occupancy.match.id].stage_item_input1_conflict = True
    elif occupancy.playing_side == 2:
        flags[occupancy.match.id].stage_item_input2_conflict = True
    else:
        flags[occupancy.match.id].referee_conflict = True


def _set_slot_overlap_conflicts(
    stages: list[StageWithStageItems],
    flags: dict[MatchId, MatchConflictFlags],
) -> None:
    """Flag any two overlapping matches that share a stage_item_input slot id.

    This is slot-id based rather than team-id based, so it flags placeholder (tentative/empty)
    slots too — a slot that isn't yet resolved to a concrete team is still a real resource that
    cannot play and/or referee two overlapping matches, exactly as the auto-scheduler and the
    frontend placement preview already assume. The team-id based checks above remain for cross-
    stage-item identity (the same team appearing under different slot ids), which a slot-id check
    cannot see; for resolved slots this check only re-flags conflicts those already cover, so
    behavior for Final slots is unchanged.
    """
    occupancies_by_slot: defaultdict[StageItemInputId, list[_SlotOccupancy]] = defaultdict(list)
    for match in _get_all_matches(stages):
        if match.start_time is None:
            continue
        slots = (
            (match.stage_item_input1_id, 1),
            (match.stage_item_input2_id, 2),
            (match.referee_stage_item_input_id, None),
        )
        for slot_id, playing_side in slots:
            if slot_id is None:
                continue
            occupancies_by_slot[slot_id].append(
                _SlotOccupancy(match, match.start_time, match.end_time, playing_side)
            )

    for occupancies in occupancies_by_slot.values():
        for i, occupancy1 in enumerate(occupancies):
            for occupancy2 in occupancies[i + 1 :]:
                if not _time_ranges_overlap(
                    occupancy1.start_time,
                    occupancy1.end_time,
                    occupancy2.start_time,
                    occupancy2.end_time,
                ):
                    continue
                _flag_slot_occupancy(occupancy1, flags)
                _flag_slot_occupancy(occupancy2, flags)


def get_match_conflict_flags(
    stages: list[StageWithStageItems], default_break_minutes: int
) -> dict[MatchId, MatchConflictFlags]:
    matches = _get_all_matches(stages)
    flags = {match.id: MatchConflictFlags() for match in matches}

    _set_team_overlap_conflicts(stages, flags)
    _set_referee_overlap_conflicts(stages, flags)
    _set_slot_overlap_conflicts(stages, flags)
    _set_winner_of_precedence_conflicts(matches, flags)
    _set_cross_stage_precedence_conflicts(stages, flags)
    _set_cross_stage_feeder_precedence_conflicts(stages, flags)
    _set_short_break_conflicts(matches, default_break_minutes, flags)

    return flags


def get_conflicting_matches(
    stages: list[StageWithStageItems],
) -> tuple[
    defaultdict[MatchId, list[bool]],
    set[MatchId],
]:
    flags = get_match_conflict_flags(stages, default_break_minutes=0)
    conflicts_to_set: defaultdict[MatchId, list[bool]] = defaultdict(lambda: [False, False])
    conflicts_to_clear = set()

    for match_id, conflict_flags in flags.items():
        if conflict_flags.stage_item_input1_conflict or conflict_flags.stage_item_input2_conflict:
            conflicts_to_set[match_id] = [
                conflict_flags.stage_item_input1_conflict,
                conflict_flags.stage_item_input2_conflict,
            ]
        else:
            conflicts_to_clear.add(match_id)

    assert set(conflicts_to_set.keys()).intersection(conflicts_to_clear) == set()
    return conflicts_to_set, conflicts_to_clear


async def set_conflicts(match_conflicts: dict[MatchId, MatchConflictFlags]) -> None:
    for match_id, conflict in match_conflicts.items():
        await database.execute(
            """
            UPDATE matches
            SET
                stage_item_input1_conflict = :stage_item_input1_conflict,
                stage_item_input2_conflict = :stage_item_input2_conflict,
                precedence_conflict = :precedence_conflict,
                short_break_conflict = :short_break_conflict,
                referee_conflict = :referee_conflict
            WHERE id = :match_id
            """,
            values={
                "match_id": match_id,
                "stage_item_input1_conflict": conflict.stage_item_input1_conflict,
                "stage_item_input2_conflict": conflict.stage_item_input2_conflict,
                "precedence_conflict": conflict.precedence_conflict,
                "short_break_conflict": conflict.short_break_conflict,
                "referee_conflict": conflict.referee_conflict,
            },
        )


async def reconcile_conflicts(tournament_id: TournamentId) -> None:
    from bracket.sql.stages import get_full_tournament_details
    from bracket.sql.tournaments import sql_get_tournament

    stages = await get_full_tournament_details(tournament_id)
    if len(stages) < 1:
        return

    tournament = await sql_get_tournament(tournament_id)
    await handle_conflicts(stages, tournament.margin_minutes)


async def handle_conflicts(stages: list[StageWithStageItems], default_break_minutes: int) -> None:
    await set_conflicts(get_match_conflict_flags(stages, default_break_minutes))
