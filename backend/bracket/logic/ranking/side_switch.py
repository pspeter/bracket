def should_show_side_switch_reminder(combined_score: int, n: int | None) -> bool:
    if n is None or combined_score == 0:
        return False
    return combined_score % n == 0
