from app.application.first_screen import (
    join_bubbles,
    merge_first_screen_into_policy,
    read_first_screen,
    split_welcome_to_bubbles,
)


def test_split_and_join():
    assert split_welcome_to_bubbles("a\n\nb\n\nc") == ["a", "b", "c"]
    assert join_bubbles(["a", "b"]) == "a\n\nb"


def test_merge_policy():
    pol, joined = merge_first_screen_into_policy(
        {}, bubbles=["안녕", "둘째"], first_delay_ms=200, bubble_gap_ms=500
    )
    assert joined == "안녕\n\n둘째"
    fs = read_first_screen(pol, "")
    assert fs["bubbles"] == ["안녕", "둘째"]
    assert fs["first_delay_ms"] == 200
    assert fs["bubble_gap_ms"] == 500
