from bracket.utils.sorting import natural_sort_key


def test_numbered_names_sort_numerically() -> None:
    names = ["c1", "c10", "c11", "c12", "c2", "c3"]
    assert sorted(names, key=natural_sort_key) == ["c1", "c2", "c3", "c10", "c11", "c12"]


def test_numbered_names_with_spaces_sort_numerically() -> None:
    names = ["Court 10", "Court 2", "Court 1"]
    assert sorted(names, key=natural_sort_key) == ["Court 1", "Court 2", "Court 10"]


def test_plain_numbers_sort_numerically() -> None:
    names = ["10", "2", "1", "12"]
    assert sorted(names, key=natural_sort_key) == ["1", "2", "10", "12"]


def test_sorting_is_case_insensitive() -> None:
    names = ["b court", "A court", "C court"]
    assert sorted(names, key=natural_sort_key) == ["A court", "b court", "C court"]


def test_mixed_text_and_numbered_names() -> None:
    names = ["Court 2", "Center Court", "Court 10"]
    assert sorted(names, key=natural_sort_key) == ["Center Court", "Court 2", "Court 10"]
