"""Unit tests for the row normalizer in ``bracket.sql.rows``.

See ``bracket/sql/rows.py`` for why this normalization exists: the ``to_json(array_agg(...))``
queries in ``bracket/sql/stages.py`` produce ``[None]`` for empty ``LEFT JOIN`` aggregates and
return the outermost aggregated column as a JSON string, while nested aggregates arrive already
parsed.
"""

import json
from typing import Any, cast

from bracket.sql.rows import normalize_stage_row


def _base_stage_row(stage_items: object) -> dict[str, object]:
    return {
        "id": 1,
        "name": "Stage",
        "tournament_id": 1,
        "level_id": None,
        "stage_items": stage_items,
    }


def test_empty_stage_items_aggregate_becomes_empty_list() -> None:
    row = normalize_stage_row(_base_stage_row([None]))
    assert row["stage_items"] == []


def test_none_stage_items_aggregate_becomes_empty_list() -> None:
    row = normalize_stage_row(_base_stage_row(None))
    assert row["stage_items"] == []


def test_stage_items_json_string_is_parsed() -> None:
    stage_item = {"id": 10, "rounds": [None], "inputs": None}
    row = normalize_stage_row(_base_stage_row(json.dumps([stage_item])))
    assert row["stage_items"] == [{"id": 10, "rounds": [], "inputs": []}]


def test_json_string_of_empty_aggregate_becomes_empty_list() -> None:
    row = normalize_stage_row(_base_stage_row(json.dumps([None])))
    assert row["stage_items"] == []


def test_empty_rounds_and_inputs_aggregates_become_empty_lists() -> None:
    stage_item = {"id": 10, "rounds": [None], "inputs": [None]}
    row = normalize_stage_row(_base_stage_row([stage_item]))
    [normalized_stage_item] = cast("list[dict[str, Any]]", row["stage_items"])
    assert normalized_stage_item["rounds"] == []
    assert normalized_stage_item["inputs"] == []


def test_none_rounds_and_inputs_aggregates_become_empty_lists() -> None:
    stage_item = {"id": 10, "rounds": None, "inputs": None}
    row = normalize_stage_row(_base_stage_row([stage_item]))
    [normalized_stage_item] = cast("list[dict[str, Any]]", row["stage_items"])
    assert normalized_stage_item["rounds"] == []
    assert normalized_stage_item["inputs"] == []


def test_empty_matches_aggregate_on_a_round_becomes_empty_list() -> None:
    stage_item = {"id": 10, "rounds": [{"id": 100, "matches": [None]}], "inputs": []}
    row = normalize_stage_row(_base_stage_row([stage_item]))
    [normalized_stage_item] = cast("list[dict[str, Any]]", row["stage_items"])
    [normalized_round] = normalized_stage_item["rounds"]
    assert normalized_round["matches"] == []


def test_clean_rows_pass_through_unchanged() -> None:
    stage_item = {
        "id": 10,
        "rounds": [{"id": 100, "matches": [{"id": 1000}]}],
        "inputs": [{"id": 5}],
    }
    row = normalize_stage_row(_base_stage_row([stage_item]))
    assert row["stage_items"] == [
        {
            "id": 10,
            "rounds": [{"id": 100, "matches": [{"id": 1000}]}],
            "inputs": [{"id": 5}],
        }
    ]


def test_does_not_mutate_the_input_row() -> None:
    stage_item = {"id": 10, "rounds": [None], "inputs": [None]}
    original_row = _base_stage_row([stage_item])
    row = normalize_stage_row(original_row)

    assert row is not original_row
    assert original_row["stage_items"] == [stage_item]
