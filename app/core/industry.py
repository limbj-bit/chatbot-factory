"""Canonical store industry keys + short aliases (chat counsel, RAG, labels)."""
from typing import Optional

INDUSTRY_KR = {
    "fresh_food": "신선식품/식품",
    "beauty": "뷰티/화장품",
    "fashion": "패션/의류",
    "electronics": "전자/가전",
    "pet_supplies": "반려동물용품",
    "raw_materials": "원료/B2B",
    "baby_kids": "유아동",
    "sports_leisure": "스포츠/레저",
    "medical_clinic": "병원/클리닉",
    "education_academy": "교육/학원",
    "professional_legal": "법률/세무/전문직",
    "interior_realestate": "인테리어/건축",
    "hotel_travel": "호텔/숙박",
    "it_corporate": "IT/SaaS",
    "restaurant_cafe": "레스토랑/카페",
    "general": "종합몰",
}

# Short aliases → INDUSTRY_DEFAULTS canonical keys
INDUSTRY_ALIASES = {
    "pet": "pet_supplies",
    "kids": "baby_kids",
    "baby": "baby_kids",
    "clinic": "medical_clinic",
    "medical": "medical_clinic",
    "education": "education_academy",
    "academy": "education_academy",
    "legal": "professional_legal",
    "interior": "interior_realestate",
    "hotel": "hotel_travel",
    "travel": "hotel_travel",
    "it": "it_corporate",
    "saas": "it_corporate",
    "restaurant": "restaurant_cafe",
    "cafe": "restaurant_cafe",
    "raw": "raw_materials",
    "sports": "sports_leisure",
    "leisure": "sports_leisure",
}


def normalize_industry_key(industry: Optional[str]) -> str:
    """Map store industry / short aliases onto INDUSTRY_DEFAULTS keys."""
    key = (industry or "general").strip().lower()
    key = INDUSTRY_ALIASES.get(key, key)
    if key in INDUSTRY_KR:
        return key
    return "general"
