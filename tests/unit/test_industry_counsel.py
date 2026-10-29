"""Industry-specific counselor keywords + persona depth."""
from app.application.chat_service import ChatService, _INDUSTRY_COUNSEL, _counsel_keywords
from app.core.industry import normalize_industry_key
from app.application.store_service import INDUSTRY_DEFAULTS


def test_normalize_industry_aliases():
    assert normalize_industry_key("pet") == "pet_supplies"
    assert normalize_industry_key("pet_supplies") == "pet_supplies"
    assert normalize_industry_key("kids") == "baby_kids"
    assert normalize_industry_key("clinic") == "medical_clinic"
    assert normalize_industry_key("saas") == "it_corporate"
    assert normalize_industry_key("  Beauty ") == "beauty"
    assert normalize_industry_key("unknown_xyz") == "general"


def test_counsel_covers_all_industry_defaults_keys():
    for key in INDUSTRY_DEFAULTS:
        assert key in _INDUSTRY_COUNSEL, f"missing counsel pack: {key}"
        rec, detail = _counsel_keywords(key)
        assert rec and detail


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


def test_pet_alias_uses_pet_supplies_keywords():
    via_alias = _counsel_keywords("pet")
    via_canon = _counsel_keywords("pet_supplies")
    assert via_alias == via_canon
    assert "사료" in via_alias[0] or "사료" in via_alias[1]


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

    baby = "\n".join(ChatService._industry_persona_lines("kids", "키즈봇", "유아동"))
    assert "월령" in baby or "개월" in baby

    clinic = "\n".join(ChatService._industry_persona_lines("medical_clinic", "병원봇", "병원"))
    assert "진단" in clinic or "응급" in clinic

    hotel = "\n".join(ChatService._industry_persona_lines("hotel", "호텔봇", "호텔"))
    assert "체크인" in hotel or "예약" in hotel
