"""Row-shape normalization for the ``to_json(array_agg(...))`` queries in ``sql/stages.py``.

``get_full_tournament_details`` builds a ``StageWithStageItems`` tree by repeatedly
``LEFT JOIN``-ing and ``array_agg``-ing rounds onto stage items, matches onto rounds, and
stage items onto stages. Two artifacts of that pattern leak into the raw row:

- An empty ``LEFT JOIN`` aggregate comes back as ``[None]`` (a one-element array containing a
  SQL NULL) rather than an empty array, because ``array_agg`` over zero joined rows still
  aggregates the one placeholder NULL row that the outer join produces.
- The outermost aggregated column (``stage_items``) is returned by the driver as a JSON string
  rather than an already-parsed Python value, while the columns nested inside it (``rounds``,
  ``matches``, ``inputs``) come back already parsed, because they were embedded verbatim by
  Postgres's ``to_json`` when the outer document was built.

This module is the single place that knows about those quirks. It turns a raw row (as returned
by ``dict(x._mapping)``) into a clean nested structure -- ``[None]`` and ``None`` aggregates
become ``[]``, and the JSON-string form is parsed -- so that ``StageWithStageItems.model_validate``
only ever sees clean data and its validators don't need to reason about SQL artifacts.
"""

import json
from typing import Any


def _clean_aggregate(values: Any) -> list[Any]:
    """Normalize a ``to_json(array_agg(...))`` column into a plain list.

    Handles the three shapes such a column can arrive in: ``None`` (no aggregation happened),
    ``[None]`` (an empty ``LEFT JOIN`` was aggregated), or a real list that may still contain
    ``None`` placeholders.
    """
    if values is None:
        return []
    return [value for value in values if value is not None]


def _normalize_round_row(round_row: dict[str, Any]) -> dict[str, Any]:
    round_row = dict(round_row)
    round_row["matches"] = _clean_aggregate(round_row.get("matches"))
    return round_row


def _normalize_stage_item_row(stage_item_row: dict[str, Any]) -> dict[str, Any]:
    stage_item_row = dict(stage_item_row)
    stage_item_row["rounds"] = [
        _normalize_round_row(round_row)
        for round_row in _clean_aggregate(stage_item_row.get("rounds"))
    ]
    stage_item_row["inputs"] = _clean_aggregate(stage_item_row.get("inputs"))
    return stage_item_row


def normalize_stage_row(stage_row: dict[str, Any]) -> dict[str, Any]:
    """Clean a raw ``stages`` row (with its nested ``stage_items``/``rounds``/``matches``
    aggregates) so it is safe to pass to ``StageWithStageItems.model_validate``.

    This is the row-shape contract of the ``to_json(array_agg(...))`` queries in
    ``sql/stages.py``: the models receive clean data and no longer need to know how the SQL
    aggregated it.
    """
    stage_row = dict(stage_row)
    stage_items = stage_row.get("stage_items")
    if isinstance(stage_items, str):
        stage_items = json.loads(stage_items)

    stage_row["stage_items"] = [
        _normalize_stage_item_row(stage_item_row)
        for stage_item_row in _clean_aggregate(stage_items)
    ]
    return stage_row
