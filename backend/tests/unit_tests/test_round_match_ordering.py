"""Unit guarantee that rounds and matches always come out in a stable, deterministic id order.

The database query orders these explicitly, but the model layer enforces the same contract as
defense-in-depth: it cannot silently regress the way a hand-edited SQL ``array_agg`` can, and it
keeps round-1 logic (Swiss resolution) always seeing the real round 1 first.
"""

from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.dummy_records import (
    DUMMY_MATCH1,
    DUMMY_ROUND1,
    DUMMY_STAGE_ITEM1,
)


def _match_dict(match_id: int) -> dict[str, object]:
    return {**DUMMY_MATCH1.model_dump(), "id": match_id}


def _round_dict(round_id: int, match_ids: list[int]) -> dict[str, object]:
    return {
        **DUMMY_ROUND1.model_dump(),
        "id": round_id,
        "matches": [_match_dict(match_id) for match_id in match_ids],
    }


def test_matches_are_sorted_by_id() -> None:
    round_ = RoundWithMatches.model_validate(_round_dict(1, [30, 10, 20]))
    assert [match.id for match in round_.matches] == [10, 20, 30]


def test_rounds_are_sorted_by_id_and_so_are_their_matches() -> None:
    stage_item = StageItemWithRounds.model_validate(
        {
            **DUMMY_STAGE_ITEM1.model_dump(),
            "id": 1,
            "inputs": [],
            "rounds": [
                _round_dict(3, [102, 101]),
                _round_dict(1, [2, 1]),
                _round_dict(2, [50, 40]),
            ],
        }
    )

    assert [round_.id for round_ in stage_item.rounds] == [1, 2, 3]
    for round_ in stage_item.rounds:
        match_ids = [match.id for match in round_.matches]
        assert match_ids == sorted(match_ids)
