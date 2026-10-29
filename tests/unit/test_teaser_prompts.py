from app.domain.teaser_prompts import get_teaser_prompts


def test_beauty_teasers_differ_from_fresh_food():
    beauty = get_teaser_prompts("beauty", "루이")
    food = get_teaser_prompts("fresh_food", "신선봇")
    assert any("피부" in t or "성분" in t for t in beauty)
    assert any("보관" in t or "변질" in t or "알레르기" in t for t in food)
    assert beauty != food
    assert all("루이" in t or "물어" in t or "진단" in t or "성분" in t or "피부" in t or "파손" in t for t in beauty[:1]) or "루이" in beauty[0]


def test_bot_name_interpolated():
    lines = get_teaser_prompts("beauty", "루이")
    assert lines[0] == "안녕하세요, 상담사 루이입니다 ✨"


def test_unknown_industry_falls_back_to_general():
    lines = get_teaser_prompts("wedding_consulting", "아리봇")
    assert "아리봇" in lines[0]
    assert len(lines) >= 4
