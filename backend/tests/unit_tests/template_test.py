import pytest

from bracket.logic.planning.template import (
    BlueprintInput,
    TemplateConfig,
    build_template_blueprint,
)
from bracket.models.db.stage_item import StageType


def make_config(**kwargs):  # type: ignore[no-untyped-def]
    defaults = dict(
        groups=4,
        total_teams=16,
        until_rank=2,
        include_semi_final=True,
        group_stage_type=StageType.ROUND_ROBIN,
    )
    return TemplateConfig(**{**defaults, **kwargs})


def stage_names(bp):  # type: ignore[no-untyped-def]
    return [s.name for s in bp.stages]


def items_in(bp, stage_name):  # type: ignore[no-untyped-def]
    (stage,) = [s for s in bp.stages if s.name == stage_name]
    return stage.items


def item_names_in(bp, stage_name):  # type: ignore[no-untyped-def]
    return [item.name for item in items_in(bp, stage_name)]


# ---------------------------------------------------------------------------
# 4 groups
# ---------------------------------------------------------------------------


def test_4_groups_until_rank_2_stage_names() -> None:
    bp = build_template_blueprint(make_config(groups=4, total_teams=16, until_rank=2))
    assert stage_names(bp) == ["Group Phase", "Semi-finals", "Finals"]


def test_4_groups_until_rank_2_group_items() -> None:
    bp = build_template_blueprint(make_config(groups=4, total_teams=16, until_rank=2))

    group_items = items_in(bp, "Group Phase")
    assert len(group_items) == 4
    assert [item.name for item in group_items] == ["Group A", "Group B", "Group C", "Group D"]
    assert all(item.type == StageType.ROUND_ROBIN for item in group_items)
    assert all(item.team_count == 4 for item in group_items)
    assert all(
        inp == BlueprintInput(slot=i + 1, winner_from=None, winner_position=None)
        for item in group_items
        for i, inp in enumerate(item.inputs)
    )


def test_4_groups_until_rank_2_semis_and_final() -> None:
    bp = build_template_blueprint(make_config(groups=4, total_teams=16, until_rank=2))

    assert item_names_in(bp, "Semi-finals") == ["Semi-final A", "Semi-final B"]
    assert item_names_in(bp, "Finals") == ["Final"]

    semi_a, semi_b = items_in(bp, "Semi-finals")
    assert semi_a.type == StageType.SINGLE_ELIMINATION
    assert semi_a.team_count == 2
    assert semi_a.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group C", winner_position=1),
    ]
    assert semi_b.inputs == [
        BlueprintInput(slot=1, winner_from="Group B", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group D", winner_position=1),
    ]

    (final,) = items_in(bp, "Finals")
    assert final.name == "Final"
    assert final.team_count == 2
    assert final.inputs == [
        BlueprintInput(slot=1, winner_from="Semi-final A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Semi-final B", winner_position=1),
    ]


def test_4_groups_until_rank_4() -> None:
    bp = build_template_blueprint(make_config(groups=4, until_rank=4))
    assert item_names_in(bp, "Semi-finals") == ["Semi-final A", "Semi-final B"]
    assert item_names_in(bp, "Finals") == ["Final", "3rd Place"]

    third = items_in(bp, "Finals")[1]
    assert third.inputs == [
        BlueprintInput(slot=1, winner_from="Semi-final A", winner_position=2),
        BlueprintInput(slot=2, winner_from="Semi-final B", winner_position=2),
    ]


def test_4_groups_until_rank_6() -> None:
    bp = build_template_blueprint(make_config(groups=4, until_rank=6))
    assert item_names_in(bp, "Semi-finals") == [
        "Semi-final A", "Semi-final B", "5th-8th Semi A", "5th-8th Semi B",
    ]
    assert item_names_in(bp, "Finals") == ["Final", "3rd Place", "5th Place"]

    semi_5a = items_in(bp, "Semi-finals")[2]
    assert semi_5a.inputs == [
        BlueprintInput(slot=1, winner_from="Group B", winner_position=2),
        BlueprintInput(slot=2, winner_from="Group D", winner_position=2),
    ]
    fifth = items_in(bp, "Finals")[2]
    assert fifth.inputs == [
        BlueprintInput(slot=1, winner_from="5th-8th Semi A", winner_position=1),
        BlueprintInput(slot=2, winner_from="5th-8th Semi B", winner_position=1),
    ]


def test_4_groups_until_rank_8() -> None:
    bp = build_template_blueprint(make_config(groups=4, until_rank=8))
    assert item_names_in(bp, "Semi-finals") == [
        "Semi-final A", "Semi-final B", "5th-8th Semi A", "5th-8th Semi B",
    ]
    assert item_names_in(bp, "Finals") == ["Final", "3rd Place", "5th Place", "7th Place"]

    seventh = items_in(bp, "Finals")[3]
    assert seventh.inputs == [
        BlueprintInput(slot=1, winner_from="5th-8th Semi A", winner_position=2),
        BlueprintInput(slot=2, winner_from="5th-8th Semi B", winner_position=2),
    ]


def test_4_groups_all_resolves_to_rank_8() -> None:
    bp_all = build_template_blueprint(make_config(groups=4, until_rank="all"))
    bp_8 = build_template_blueprint(make_config(groups=4, until_rank=8))
    assert item_names_in(bp_all, "Finals") == item_names_in(bp_8, "Finals")
    assert item_names_in(bp_all, "Semi-finals") == item_names_in(bp_8, "Semi-finals")


# ---------------------------------------------------------------------------
# 2 groups + semi-final
# ---------------------------------------------------------------------------


def make_2g_sf(**kwargs):  # type: ignore[no-untyped-def]
    return make_config(groups=2, total_teams=12, include_semi_final=True, **kwargs)


def test_2_groups_sf_until_rank_2_stage_names() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=2))
    assert stage_names(bp) == ["Group Phase", "Semi-finals", "Finals"]


def test_2_groups_sf_group_items() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=2))
    group_items = items_in(bp, "Group Phase")
    assert [item.name for item in group_items] == ["Group A", "Group B"]
    assert all(item.team_count == 6 for item in group_items)


def test_2_groups_sf_seeding() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=2))
    semi_a, semi_b = items_in(bp, "Semi-finals")
    assert semi_a.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=2),
    ]
    assert semi_b.inputs == [
        BlueprintInput(slot=1, winner_from="Group B", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group A", winner_position=2),
    ]
    (final,) = items_in(bp, "Finals")
    assert final.inputs == [
        BlueprintInput(slot=1, winner_from="Semi-final A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Semi-final B", winner_position=1),
    ]


def test_2_groups_sf_until_rank_4() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=4))
    assert item_names_in(bp, "Semi-finals") == ["Semi-final A", "Semi-final B"]
    assert item_names_in(bp, "Finals") == ["Final", "3rd Place"]

    third = items_in(bp, "Finals")[1]
    assert third.inputs == [
        BlueprintInput(slot=1, winner_from="Semi-final A", winner_position=2),
        BlueprintInput(slot=2, winner_from="Semi-final B", winner_position=2),
    ]


def test_2_groups_sf_until_rank_6() -> None:
    # make_2g_sf uses 12 teams (6 per group), so rank 6 is valid
    bp = build_template_blueprint(make_2g_sf(until_rank=6))
    # semis stage only ever contains the two main semi-finals — no 5th-8th sub-bracket
    assert item_names_in(bp, "Semi-finals") == ["Semi-final A", "Semi-final B"]
    assert item_names_in(bp, "Finals") == ["Final", "3rd Place", "5th Place"]

    # 5th place uses group position 3 directly (not semi-final losers)
    fifth = items_in(bp, "Finals")[2]
    assert fifth.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=3),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=3),
    ]


def test_2_groups_sf_until_rank_8() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=8))
    assert item_names_in(bp, "Semi-finals") == ["Semi-final A", "Semi-final B"]
    assert item_names_in(bp, "Finals") == ["Final", "3rd Place", "5th Place", "7th Place"]

    seventh = items_in(bp, "Finals")[3]
    assert seventh.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=4),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=4),
    ]


def test_2_groups_sf_all_resolves_to_2x_teams_per_group() -> None:
    # 12 teams, 2 groups → 6 per group → max rank 12
    bp = build_template_blueprint(make_2g_sf(until_rank="all"))
    assert item_names_in(bp, "Semi-finals") == ["Semi-final A", "Semi-final B"]
    ko_items = items_in(bp, "Finals")
    assert ko_items[0].name == "Final"
    assert ko_items[-1].inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=6),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=6),
    ]


def test_2_groups_sf_4_teams_raises() -> None:
    with pytest.raises(ValueError, match="teams per group must be at least 3"):
        build_template_blueprint(make_config(groups=2, total_teams=4, include_semi_final=True, until_rank=2))


def test_2_groups_sf_rank_exceeds_team_count_raises() -> None:
    # 6 teams, 2 groups → 3 per group → max rank 6; until_rank=8 should fail
    with pytest.raises(ValueError, match="until_rank.*exceeds maximum"):
        build_template_blueprint(make_config(groups=2, total_teams=6, include_semi_final=True, until_rank=8))


# ---------------------------------------------------------------------------
# 2 groups, no semi-final
# ---------------------------------------------------------------------------


def make_2g_nosf(**kwargs):  # type: ignore[no-untyped-def]
    # 12 teams → 6 per group → max rank 12
    return make_config(groups=2, total_teams=12, include_semi_final=False, **kwargs)


def test_2_groups_nosf_stage_names() -> None:
    bp = build_template_blueprint(make_2g_nosf(until_rank=2))
    assert stage_names(bp) == ["Group Phase", "Finals"]


def test_2_groups_nosf_until_rank_2() -> None:
    bp = build_template_blueprint(make_2g_nosf(until_rank=2))
    ko_items = items_in(bp, "Finals")
    assert len(ko_items) == 1
    assert ko_items[0].name == "Final"
    assert ko_items[0].inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=1),
    ]


def test_2_groups_nosf_until_rank_4() -> None:
    bp = build_template_blueprint(make_2g_nosf(until_rank=4))
    assert item_names_in(bp, "Finals") == ["Final", "3rd Place"]
    third = items_in(bp, "Finals")[1]
    assert third.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=2),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=2),
    ]


def test_2_groups_nosf_until_rank_6() -> None:
    bp = build_template_blueprint(make_2g_nosf(until_rank=6))
    assert item_names_in(bp, "Finals") == ["Final", "3rd Place", "5th Place"]
    fifth = items_in(bp, "Finals")[2]
    assert fifth.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=3),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=3),
    ]


def test_2_groups_nosf_all_resolves_to_teams_per_group_times_2() -> None:
    bp = build_template_blueprint(make_2g_nosf(until_rank="all"))
    ko_items = items_in(bp, "Finals")
    assert len(ko_items) == 6
    assert ko_items[0].name == "Final"
    assert ko_items[-1].inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=6),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=6),
    ]


def test_2_groups_nosf_swiss_group_stage() -> None:
    bp = build_template_blueprint(
        make_config(
            groups=2, total_teams=12, include_semi_final=False,
            until_rank=2, group_stage_type=StageType.SWISS,
        )
    )
    assert all(item.type == StageType.SWISS for item in items_in(bp, "Group Phase"))


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_uneven_2_groups_group_sizes() -> None:
    # 7 teams, 2 groups → Group A: 4 slots, Group B: 3 slots
    bp = build_template_blueprint(make_config(groups=2, total_teams=7, include_semi_final=False, until_rank=2))
    group_a, group_b = items_in(bp, "Group Phase")
    assert group_a.team_count == 4
    assert len(group_a.inputs) == 4
    assert group_b.team_count == 3
    assert len(group_b.inputs) == 3


def test_uneven_4_groups_group_sizes() -> None:
    # 17 teams, 4 groups → Group A: 5 slots, Groups B/C/D: 4 slots each
    bp = build_template_blueprint(make_config(groups=4, total_teams=17, until_rank=2))
    group_items = items_in(bp, "Group Phase")
    assert group_items[0].team_count == 5  # Group A gets the extra team
    assert all(item.team_count == 4 for item in group_items[1:])


def test_uneven_groups_knockout_uses_min_team_count() -> None:
    # 7 teams, 2 groups → floor=3, max_rank=6; knockout references only positions 1–3
    bp = build_template_blueprint(make_config(groups=2, total_teams=7, include_semi_final=False, until_rank="all"))
    ko_items = items_in(bp, "Finals")
    assert len(ko_items) == 3  # Final, 3rd, 5th — not 4th rank (position 4 doesn't advance)
    assert ko_items[-1].inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=3),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=3),
    ]


def test_uneven_2_groups_sf_valid() -> None:
    # 7 teams, 2 groups with SF → floor=3 ≥ min 3, should not raise
    bp = build_template_blueprint(make_config(groups=2, total_teams=7, include_semi_final=True, until_rank=2))
    assert stage_names(bp) == ["Group Phase", "Semi-finals", "Finals"]
    group_a, group_b = items_in(bp, "Group Phase")
    assert group_a.team_count == 4
    assert group_b.team_count == 3


def test_odd_until_rank_raises() -> None:
    with pytest.raises(ValueError, match="until_rank must be even"):
        build_template_blueprint(make_config(until_rank=3))


def test_until_rank_exceeds_max_raises() -> None:
    with pytest.raises(ValueError, match="until_rank.*exceeds maximum"):
        build_template_blueprint(make_config(groups=4, until_rank=10))


def test_total_teams_too_low_raises() -> None:
    with pytest.raises(ValueError, match="total_teams must be at least"):
        build_template_blueprint(make_config(groups=2, total_teams=2))


def test_until_rank_zero_raises() -> None:
    with pytest.raises(ValueError, match="until_rank must be at least 2"):
        build_template_blueprint(make_config(until_rank=0))


def test_negative_until_rank_raises() -> None:
    with pytest.raises(ValueError, match="until_rank must be at least 2"):
        build_template_blueprint(make_config(until_rank=-2))


def test_one_team_per_group_raises() -> None:
    with pytest.raises(ValueError, match="teams per group must be at least 2"):
        build_template_blueprint(make_config(groups=4, total_teams=4))


def test_4_groups_ignores_include_semi_final_false() -> None:
    bp_true = build_template_blueprint(make_config(groups=4, include_semi_final=True, until_rank=4))
    bp_false = build_template_blueprint(make_config(groups=4, include_semi_final=False, until_rank=4))
    assert stage_names(bp_true) == stage_names(bp_false)
    assert item_names_in(bp_true, "Semi-finals") == item_names_in(bp_false, "Semi-finals")
