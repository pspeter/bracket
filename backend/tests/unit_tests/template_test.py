from bracket.logic.planning.template import (
    BlueprintInput,
    BlueprintStage,
    BlueprintStageItem,
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


# ---------------------------------------------------------------------------
# 4 groups
# ---------------------------------------------------------------------------


def test_4_groups_until_rank_2_stage_structure() -> None:
    bp = build_template_blueprint(make_config(groups=4, total_teams=16, until_rank=2))

    assert len(bp.stages) == 2
    assert bp.stages[0].name == "Group Phase"
    assert bp.stages[1].name == "Knockout Phase"


def test_4_groups_until_rank_2_group_items() -> None:
    bp = build_template_blueprint(make_config(groups=4, total_teams=16, until_rank=2))

    group_items = bp.stages[0].items
    assert len(group_items) == 4
    assert [item.name for item in group_items] == ["Group A", "Group B", "Group C", "Group D"]
    assert all(item.type == StageType.ROUND_ROBIN for item in group_items)
    assert all(item.team_count == 4 for item in group_items)
    # each group slot is empty (teams assigned manually later)
    assert all(
        inp == BlueprintInput(slot=i + 1, winner_from=None, winner_position=None)
        for item in group_items
        for i, inp in enumerate(item.inputs)
    )


def test_4_groups_until_rank_2_knockout_items() -> None:
    bp = build_template_blueprint(make_config(groups=4, total_teams=16, until_rank=2))

    ko_items = bp.stages[1].items
    assert len(ko_items) == 3  # Semi A, Semi B, Final

    semi_a, semi_b, final = ko_items
    assert semi_a.name == "Semi-final A"
    assert semi_a.type == StageType.SINGLE_ELIMINATION
    assert semi_a.team_count == 2
    assert semi_a.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group C", winner_position=1),
    ]

    assert semi_b.name == "Semi-final B"
    assert semi_b.inputs == [
        BlueprintInput(slot=1, winner_from="Group B", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group D", winner_position=1),
    ]

    assert final.name == "Final"
    assert final.team_count == 2
    assert final.inputs == [
        BlueprintInput(slot=1, winner_from="Semi-final A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Semi-final B", winner_position=1),
    ]


def test_4_groups_until_rank_4() -> None:
    bp = build_template_blueprint(make_config(groups=4, until_rank=4))
    ko_names = [item.name for item in bp.stages[1].items]
    assert ko_names == ["Semi-final A", "Semi-final B", "Final", "3rd Place"]
    third = bp.stages[1].items[3]
    assert third.inputs == [
        BlueprintInput(slot=1, winner_from="Semi-final A", winner_position=2),
        BlueprintInput(slot=2, winner_from="Semi-final B", winner_position=2),
    ]


def test_4_groups_until_rank_6() -> None:
    bp = build_template_blueprint(make_config(groups=4, until_rank=6))
    ko_names = [item.name for item in bp.stages[1].items]
    assert ko_names == [
        "Semi-final A", "Semi-final B", "Final", "3rd Place",
        "5th-8th Semi A", "5th-8th Semi B", "5th Place",
    ]
    semi_5a = bp.stages[1].items[4]
    assert semi_5a.inputs == [
        BlueprintInput(slot=1, winner_from="Group B", winner_position=2),
        BlueprintInput(slot=2, winner_from="Group D", winner_position=2),
    ]
    fifth = bp.stages[1].items[6]
    assert fifth.inputs == [
        BlueprintInput(slot=1, winner_from="5th-8th Semi A", winner_position=1),
        BlueprintInput(slot=2, winner_from="5th-8th Semi B", winner_position=1),
    ]


def test_4_groups_until_rank_8() -> None:
    bp = build_template_blueprint(make_config(groups=4, until_rank=8))
    ko_names = [item.name for item in bp.stages[1].items]
    assert ko_names == [
        "Semi-final A", "Semi-final B", "Final", "3rd Place",
        "5th-8th Semi A", "5th-8th Semi B", "5th Place", "7th Place",
    ]
    seventh = bp.stages[1].items[7]
    assert seventh.inputs == [
        BlueprintInput(slot=1, winner_from="5th-8th Semi A", winner_position=2),
        BlueprintInput(slot=2, winner_from="5th-8th Semi B", winner_position=2),
    ]


def test_4_groups_all_resolves_to_rank_8() -> None:
    bp_all = build_template_blueprint(make_config(groups=4, until_rank="all"))
    bp_8 = build_template_blueprint(make_config(groups=4, until_rank=8))
    assert [item.name for item in bp_all.stages[1].items] == [
        item.name for item in bp_8.stages[1].items
    ]


# ---------------------------------------------------------------------------
# 2 groups + semi-final
# ---------------------------------------------------------------------------


def make_2g_sf(**kwargs):  # type: ignore[no-untyped-def]
    return make_config(groups=2, total_teams=12, include_semi_final=True, **kwargs)


def test_2_groups_sf_until_rank_2_structure() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=2))

    assert len(bp.stages) == 2
    group_items = bp.stages[0].items
    assert [item.name for item in group_items] == ["Group A", "Group B"]
    assert all(item.team_count == 6 for item in group_items)

    ko_names = [item.name for item in bp.stages[1].items]
    assert ko_names == ["Semi-final A", "Semi-final B", "Final"]


def test_2_groups_sf_seeding() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=2))
    semi_a, semi_b, final = bp.stages[1].items

    assert semi_a.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=2),
    ]
    assert semi_b.inputs == [
        BlueprintInput(slot=1, winner_from="Group B", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group A", winner_position=2),
    ]
    assert final.inputs == [
        BlueprintInput(slot=1, winner_from="Semi-final A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Semi-final B", winner_position=1),
    ]


def test_2_groups_sf_until_rank_4() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=4))
    ko_names = [item.name for item in bp.stages[1].items]
    assert ko_names == ["Semi-final A", "Semi-final B", "Final", "3rd Place"]
    third = bp.stages[1].items[3]
    assert third.inputs == [
        BlueprintInput(slot=1, winner_from="Semi-final A", winner_position=2),
        BlueprintInput(slot=2, winner_from="Semi-final B", winner_position=2),
    ]


def test_2_groups_sf_until_rank_6() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=6))
    ko_names = [item.name for item in bp.stages[1].items]
    assert ko_names == [
        "Semi-final A", "Semi-final B", "Final", "3rd Place",
        "5th-8th Semi A", "5th-8th Semi B", "5th Place",
    ]
    semi_5a = bp.stages[1].items[4]
    assert semi_5a.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=2),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=1),
    ]
    semi_5b = bp.stages[1].items[5]
    assert semi_5b.inputs == [
        BlueprintInput(slot=1, winner_from="Group B", winner_position=2),
        BlueprintInput(slot=2, winner_from="Group A", winner_position=1),
    ]


def test_2_groups_sf_until_rank_8() -> None:
    bp = build_template_blueprint(make_2g_sf(until_rank=8))
    ko_names = [item.name for item in bp.stages[1].items]
    assert "7th Place" in ko_names
    seventh = bp.stages[1].items[-1]
    assert seventh.inputs == [
        BlueprintInput(slot=1, winner_from="5th-8th Semi A", winner_position=2),
        BlueprintInput(slot=2, winner_from="5th-8th Semi B", winner_position=2),
    ]


def test_2_groups_sf_all_resolves_to_rank_8() -> None:
    bp_all = build_template_blueprint(make_2g_sf(until_rank="all"))
    bp_8 = build_template_blueprint(make_2g_sf(until_rank=8))
    assert [item.name for item in bp_all.stages[1].items] == [
        item.name for item in bp_8.stages[1].items
    ]


# ---------------------------------------------------------------------------
# 2 groups, no semi-final
# ---------------------------------------------------------------------------


def make_2g_nosf(**kwargs):  # type: ignore[no-untyped-def]
    # 12 teams → 6 per group → max rank 12
    return make_config(groups=2, total_teams=12, include_semi_final=False, **kwargs)


def test_2_groups_nosf_until_rank_2() -> None:
    bp = build_template_blueprint(make_2g_nosf(until_rank=2))
    ko_items = bp.stages[1].items
    assert len(ko_items) == 1
    assert ko_items[0].name == "Final"
    assert ko_items[0].inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=1),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=1),
    ]


def test_2_groups_nosf_until_rank_4() -> None:
    bp = build_template_blueprint(make_2g_nosf(until_rank=4))
    ko_names = [item.name for item in bp.stages[1].items]
    assert ko_names == ["Final", "3rd Place"]
    third = bp.stages[1].items[1]
    assert third.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=2),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=2),
    ]


def test_2_groups_nosf_until_rank_6() -> None:
    bp = build_template_blueprint(make_2g_nosf(until_rank=6))
    ko_names = [item.name for item in bp.stages[1].items]
    assert ko_names == ["Final", "3rd Place", "5th Place"]
    fifth = bp.stages[1].items[2]
    assert fifth.inputs == [
        BlueprintInput(slot=1, winner_from="Group A", winner_position=3),
        BlueprintInput(slot=2, winner_from="Group B", winner_position=3),
    ]


def test_2_groups_nosf_all_resolves_to_teams_per_group_times_2() -> None:
    # 12 teams, 2 groups → 6 per group → max rank 12 → 6 place matches
    bp = build_template_blueprint(make_2g_nosf(until_rank="all"))
    ko_items = bp.stages[1].items
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
    assert all(item.type == StageType.SWISS for item in bp.stages[0].items)
