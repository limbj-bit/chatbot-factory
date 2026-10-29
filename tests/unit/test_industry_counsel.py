"""Industry-specific counselor keywords + persona depth."""
from app.application.chat_service import ChatService, _counsel_keywords


def test_fresh_food_keywords_prefer_storage_over_skin():
    rec, detail = _counsel_keywords("fresh_food")
    assert "보관" in rec or "보관" in detail
    assert "당도" in detail
    assert "알레르기" in detail or "알러지" in detail
    assert "건성" not in detail


def test_fashion_keywords_include_size_fit():
    rec, detail = _counsel_keywords("fashion")
    assert "사이즈" in rec or "사이즈" in detail
    assert "핏" in detail or "핏" in rec


def test_persona_lines_by_industry_depth():
    beauty = "\n".join(ChatService._industry_persona_lines("beauty", "루이", "뷰티"))
    assert "인테이크" in beauty
    assert "피부타입" in beauty
    assert "답변 구조" in beauty

    fresh = "\n".join(ChatService._industry_persona_lines("fresh_food", "딸기봇", "신선식품"))
    assert "인테이크" in fresh
    assert "보관" in fresh
    assert "알레르기" in fresh or "추측" in fresh
    assert "피부" not in fresh

    fashion = "\n".join(ChatService._industry_persona_lines("fashion", "코디봇", "패션"))
    assert "사이즈" in fashion or "핏" in fashion
    assert "인테이크" in fashion

    elec = "\n".join(ChatService._industry_persona_lines("electronics", "테크봇", "전자"))
    assert "스펙" in elec or "호환" in elec

    pet = "\n".join(ChatService._industry_persona_lines("pet", "펫봇", "반려동물"))
    assert "수의사" in pet or "알러지" in pet
