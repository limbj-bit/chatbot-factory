import pytest
from app.infrastructure.rag.engine import correct_typos, expand_query_tokens, TYPO_CORRECTIONS
from app.application.chat_service import _normalize_product_query, ChatService
from app.infrastructure.database.models import StoreModel


def test_typo_correction_and_expansion():
    # 1. Direct typo corrections
    assert correct_typos("골라겐 크림") == "콜라겐 크림"
    assert correct_typos("루이셆 수딩클랜저") == "루이셀 수딩클렌저"
    assert correct_typos("피디알엔 앰플") == "pdrn 앰플"
    assert correct_typos("탈기 보관법") == "딸기 보관법"
    assert correct_typos("싸이즈 문의") == "사이즈 문의"

    # 2. expand_query_tokens includes canonical tokens
    tokens = expand_query_tokens("골라겐 크림 보여줘", industry="beauty")
    assert "콜라겐" in tokens or "탄력" in tokens

    pdrn_tokens = expand_query_tokens("피디알엔 앰플", industry="beauty")
    assert "pdrn" in pdrn_tokens

    # 3. Product query normalization with typo
    normalized = _normalize_product_query("골라겐 크림 보여줘")
    assert "콜라겐" in normalized


def test_store_custom_prompt_injected_into_system_prompt():
    store = StoreModel(
        id="store_test_01",
        mall_id="test_mall",
        store_name="루이셀테스트",
        industry="beauty",
        bot_name="루이봇",
        custom_prompt="루이셀은 30년 전통 피부과 입점 전문 화장품입니다. 오후 2시 이전 주문 당일 출고.",
    )
    prompt = ChatService._build_store_system_prompt(store)
    assert "점주 특별 전달사항" in prompt
    assert "30년 전통 피부과 입점 전문 화장품" in prompt
    assert "오후 2시 이전 주문 당일 출고" in prompt
