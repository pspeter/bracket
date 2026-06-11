import re

_DIGITS = re.compile(r"(\d+)")


def natural_sort_key(value: str) -> tuple[str | int, ...]:
    """
    Sort key that compares embedded numbers numerically, so that e.g. court names
    "c1", "c2", "c10" sort in that order instead of "c1", "c10", "c2".

    Splitting on digit runs always yields text at even indices and digits at odd
    indices, so tuple comparison never compares str to int.
    """
    return tuple(
        int(chunk) if chunk.isdigit() else chunk.casefold() for chunk in _DIGITS.split(value)
    )
