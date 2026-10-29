"""Store-policy-first FAQ + order-tracking intent (no shipping-policy hijack)."""
import json

from app.application.chat_service import ChatService
from app.infrastructure.rag.engine import RAGEngine


class _Store:
    def __init__(self, **kw):
        self.mall_id = kw.get("mall_id", "route_mall")
        self.store_name = kw.get("store_name", "라우트몰")
        self.business_hours = kw.get("business_hours", "평일 10:00~18:00")
        self.policy_config_json = kw.get(
            "policy_config_json",
            json.dumps(
                {
                    "claim_policy": {"max_claim_days": 14},
                    "shipping_policy": {
                        "delivery_fee": 2500,
                        "free_over_amount": 40000,
                        "delivery_days": "결제 후 1~2일 출고",
                        "note": "제주 추가 3,000원",
                    },
                },
                ensure_ascii=False,
            ),
        )


def test_store_policy_faq_beats_shipping_fee_and_hours():
    store = _Store()
    fee = ChatService._lookup_store_policy_faq("배송비 얼마예요?", store)
    assert fee is not None
    assert "2,500원" in fee
    assert "40,000원" in fee
    assert "3,000원" in fee  # 제주 note

    hours = ChatService._lookup_store_policy_faq("운영시간 알려주세요", store)
    assert hours is not None
    assert "평일 10:00~18:00" in hours
    assert "라우트몰" in hours

    claim = ChatService._lookup_store_policy_faq("반품 기한이 어떻게 되나요?", store)
    assert claim is not None
    assert "14일" in claim


def test_global_faq_excluded_when_store_covers_topic():
    store = _Store()
    covered = ChatService._global_faq_keywords_covered_by_store(store)
    assert "배송비" in covered
    assert "운영시간" in covered
    assert "반품정책" in covered

    rag = RAGEngine()
    # Global would say 3,000원 — must be blocked so store answer wins upstream
    assert rag.lookup_deterministic_faq("배송비 얼마예요?", exclude_keywords=covered) is None
    # Unrelated global FAQ still works
    assert rag.lookup_deterministic_faq("입금계좌 알려주세요", exclude_keywords=covered) is not None


def test_order_tracking_vs_shipping_policy_intent():
    assert ChatService._is_order_tracking_intent("ORD-NORMAL 배송 어디쯤이에요?") is True
    assert ChatService._is_order_tracking_intent("20261028-0000012 조회") is True
    assert ChatService._is_order_tracking_intent("운송장 번호 알려주세요") is True

    assert ChatService._is_order_tracking_intent("배송비 얼마예요?") is False
    assert ChatService._is_order_tracking_intent("배송 며칠 걸려요?") is False
    assert ChatService._is_order_tracking_intent("반품 배송은 어떻게 하나요?") is False


def test_no_store_falls_back_to_global_faq_keywords():
    assert ChatService._lookup_store_policy_faq("배송비 얼마예요?", None) is None
    assert ChatService._global_faq_keywords_covered_by_store(None) == set()
    rag = RAGEngine()
    assert "3,000원" in (rag.lookup_deterministic_faq("배송비 얼마예요?") or "")
