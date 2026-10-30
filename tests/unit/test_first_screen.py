from app.application.first_screen import (
    join_bubbles,
    merge_first_screen_into_policy,
    merge_teaser_into_policy,
    read_first_screen,
    read_teaser,
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


def test_teaser_defaults_from_industry():
    t = read_teaser({}, industry="beauty", bot_name="루이")
    assert any("루이" in p for p in t["prompts"])
    assert t["first_delay_ms"] == 12000
    assert t["max_shows"] == 4


def test_merge_teaser_custom():
    pol = merge_teaser_into_policy(
        {},
        prompts=["맞춤 티저", "둘째"],
        first_delay_ms=3000,
        visible_ms=2000,
        gap_ms=10000,
        max_shows=2,
    )
    t = read_teaser(pol, industry="beauty", bot_name="루이")
    assert t["prompts"] == ["맞춤 티저", "둘째"]
    assert t["first_delay_ms"] == 3000
    assert t["visible_ms"] == 2000
    assert t["gap_ms"] == 10000
    assert t["max_shows"] == 2
