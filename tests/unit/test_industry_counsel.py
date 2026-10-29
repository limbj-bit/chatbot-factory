"""Industry-specific counselor keywords + persona snippets."""
from app.application.chat_service import ChatService, _counsel_keywords


def test_fresh_food_keywords_prefer_storage_over_skin():
    rec, detail = _counsel_keywords("fresh_food")
    assert "보관" in rec or "보관" in detail
    assert "당도" in detail
    assert "건성" not in detail  # beauty-only should not gate fresh cards


def test_fashion_keywords_include_size_fit():
    rec, detail = _counsel_keywords("fashion")
    assert "사이즈" in rec or "사이즈" in detail
    assert "핏" in detail or "핏" in rec


def test_persona_lines_by_industry():
    beauty = "\n".join(ChatService._industry_persona_lines("beauty", "루이", "뷰티"))
    assert "뷰티" in beauty
    assert "피부타입" in beauty

    fresh = "\n".join(ChatService._industry_persona_lines("fresh_food", "딸기봇", "신선식품"))
    assert "보관" in fresh
    assert "피부" not in fresh

    fashion = "\n".join(ChatService._industry_persona_lines("fashion", "코디봇", "패션"))
    assert "사이즈" in fashion or "핏" in fashion
