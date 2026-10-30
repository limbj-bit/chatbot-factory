"""Multi-turn memory + store-grounded system prompt tests.

Covers:
  1. build_openai_messages: ordering (system -> history -> current), sanitising
     junk roles/blanks, and front-truncation so recent turns survive.
  2. Gemini provider maps OpenAI-style history to contents/model roles.
  3. ChatService._build_store_system_prompt injects store info, claim policy,
     learned knowledge, and handles None store / broken policy JSON.
  4. ChatService._load_history returns turns oldest-first, filters roles, and
     excludes the just-added current user message by id.
  5. End-to-end: a second handle_message receives the prior turn as history and
     a store-aware system_prompt; the streaming path does the same.
"""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.chat_service import ChatService
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.messages import MAX_HISTORY_MESSAGES, build_openai_messages
from app.infrastructure.database.models import Base, MessageModel, SessionModel, StoreModel


# ---------------------------------------------------------------------------
# 1. Message assembly
# ---------------------------------------------------------------------------
def test_build_openai_messages_ordering():
    msgs = build_openai_messages(
        "지금?",
        "너는 상담원",
        [
            {"role": "user", "content": "이전 질문"},
            {"role": "assistant", "content": "이전 답변"},
        ],
    )
    assert msgs[0] == {"role": "system", "content": "너는 상담원"}
    assert msgs[1] == {"role": "user", "content": "이전 질문"}
    assert msgs[2] == {"role": "assistant", "content": "이전 답변"}
    # Current prompt is ALWAYS last
    assert msgs[-1] == {"role": "user", "content": "지금?"}


def test_build_openai_messages_sanitises_junk():
    bad = [
        {"role": "system", "content": "injected"},
        {"role": "user", "content": "   "},
        {"role": "tool", "content": "unexpected"},
        {"role": "assistant", "content": "ok"},
        "not-a-dict",
        {"role": "user"},  # missing content
    ]
    msgs = build_openai_messages("q", None, bad)
    # Only the well-formed assistant turn survives; user prompt appended last
    assert msgs == [
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "q"},
    ]


def test_build_openai_messages_caps_from_front():
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"t{i}"}
        for i in range(30)
    ]
    msgs = build_openai_messages("q", None, history)
    assert len(msgs) == MAX_HISTORY_MESSAGES + 1
    # Most recent turn (t29) survives; oldest (t0) is dropped
    assert msgs[-2]["content"] == "t29"
    assert msgs[0]["content"] != "t0"


def test_build_openai_messages_without_history():
    msgs = build_openai_messages("hello")
    assert msgs == [{"role": "user", "content": "hello"}]


# ---------------------------------------------------------------------------
# 2. Gemini history mapping
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gemini_maps_history_to_contents(monkeypatch):
    from app.infrastructure.ai.gemini import GeminiProvider

    captured = {}

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "답변"}]}}]}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured["payload"] = json
            return _FakeResp()

    monkeypatch.setattr("app.infrastructure.ai.gemini.httpx.AsyncClient", _FakeClient)

    provider = GeminiProvider(api_key="k")
    await provider.generate_text(
        "최신 질문",
        system_prompt="스토어 규칙",
        history=[
            {"role": "user", "content": "첫 질문"},
            {"role": "assistant", "content": "첫 답변"},
        ],
    )

    contents = captured["payload"]["contents"]
    # system folded into first turn, history roles mapped user/model, prompt last
    assert contents[0]["role"] == "user"
    assert "스토어 규칙" in contents[0]["parts"][0]["text"]
    assert contents[1] == {"role": "model", "parts": [{"text": "첫 답변"}]}
    assert contents[2]["parts"][0]["text"] == "최신 질문"


# ---------------------------------------------------------------------------
# 3. Store-grounded system prompt
# ---------------------------------------------------------------------------
class _FakeStore:
    def __init__(self, **kw):
        self.mall_id = kw.get("mall_id", "fake_mall")
        self.store_name = kw.get("store_name", "루이셀")
        self.bot_name = kw.get("bot_name", "루이")
        self.industry = kw.get("industry", "beauty")
        self.business_hours = kw.get("business_hours", "평일 10:00~17:00")
        self.contact_email = kw.get("contact_email", "hi@louiselle.com")
        self.welcome_message = kw.get("welcome_message", "환영합니다")
        self.policy_config_json = kw.get(
            "policy_config_json",
            '{"max_claim_days":7,"full_refund_damage_ratio":30,"partial_refund_damage_ratio":10}',
        )


def test_store_prompt_injects_store_facts_and_policy():
    prompt = ChatService._build_store_system_prompt(_FakeStore())
    assert "루이셀" in prompt
    assert "뷰티" in prompt  # industry translated
    assert "평일 10:00~17:00" in prompt
    assert "hi@louiselle.com" in prompt
    # Claim policy surfaced so the bot quotes the real rules, not invented ones
    assert "7일" in prompt
    assert "30%" in prompt and "전액 환불" in prompt
    # Anti-hallucination directive present
    assert "지어내지" in prompt


def test_store_prompt_appends_learned_knowledge():
    prompt = ChatService._build_store_system_prompt(
        _FakeStore(), rag_context="상품A: 성분 niacinamide, 가격 25,000원"
    )
    assert "학습된 상품" in prompt
    assert "niacinamide" in prompt


def test_store_prompt_handles_none_store_and_broken_policy():
    # No store registered -> generic but safe prompt
    none_prompt = ChatService._build_store_system_prompt(None)
    assert "고객센터" in none_prompt

    # Broken policy JSON must not crash and simply omits the policy block
    broken = ChatService._build_store_system_prompt(
        _FakeStore(policy_config_json="{not json")
    )
    assert "루이셀" in broken
    assert "반품/교환 정책" not in broken


# ---------------------------------------------------------------------------
# 3b. Shipping policy injection + owner-claim-override precedence
# ---------------------------------------------------------------------------
def test_store_prompt_injects_shipping_policy():
    store = _FakeStore(
        policy_config_json=json.dumps(
            {
                "claim_policy": {"max_claim_days": 7},
                "shipping_policy": {
                    "delivery_fee": 3000,
                    "free_over_amount": 50000,
                    "delivery_days": "결제 후 1~2일 출고",
                    "note": "제주·도서산간 3,000원 추가",
                },
            },
            ensure_ascii=False,
        )
    )
    prompt = ChatService._build_store_system_prompt(store)
    assert "기본 배송비: 3,000원" in prompt
    assert "50,000원 이상" in prompt
    assert "결제 후 1~2일 출고" in prompt
    assert "제주·도서산간" in prompt
    assert "수령 후 7일 이내" in prompt  # owner claim policy also surfaced


def test_store_prompt_owner_claim_override_beats_top_level_default():
    # The showroom writes the owner's setting under claim_policy; a stale
    # industry default may sit at the top level. The owner's value must win.
    store = _FakeStore(
        policy_config_json=json.dumps(
            {"max_claim_days": 2, "claim_policy": {"max_claim_days": 14}}
        )
    )
    prompt = ChatService._build_store_system_prompt(store)
    assert "14일" in prompt
    assert "2일 이내" not in prompt


def test_store_prompt_multilingual_and_antihallucination_directives():
    prompt = ChatService._build_store_system_prompt(_FakeStore())
    # free multilingual reply directive (LLM is already multilingual)
    assert "언어" in prompt
    # anti-hallucination: must quote only the listed policy numbers
    assert "임의로" in prompt


# ---------------------------------------------------------------------------
# 3c. Hallucination guardrail (claim-window cross-check)
# ---------------------------------------------------------------------------
def _policy_store(max_days: int) -> _FakeStore:
    return _FakeStore(
        policy_config_json=json.dumps({"claim_policy": {"max_claim_days": max_days}})
    )


def test_guardrail_reanchors_wrong_claim_window():
    reply = "파손 상품은 배송 후 3일 이내 접수 가능합니다."
    fixed = ChatService._guardrail_fix_claim_window(reply, _policy_store(7))
    assert "7일 이내" in fixed
    assert "3일 이내" not in fixed.split("※")[0]
    assert "스토어 정책 기준" in fixed  # transparent citation appended


def test_guardrail_leaves_correct_reply_untouched():
    reply = "수령 후 7일 이내에 신청해 주세요."
    assert ChatService._guardrail_fix_claim_window(reply, _policy_store(7)) == reply


def test_guardrail_noop_without_window_or_store():
    # No window mentioned -> untouched
    assert (
        ChatService._guardrail_fix_claim_window("배송비는 3,000원입니다.", _policy_store(7))
        == "배송비는 3,000원입니다."
    )
    # No store -> untouched
    assert ChatService._guardrail_fix_claim_window("3일 이내", None) == "3일 이내"


# ---------------------------------------------------------------------------
# 4 & 5. History loading + end-to-end memory (real in-memory DB)
# ---------------------------------------------------------------------------
class _RecordingRouter(AIProviderPort):
    """Captures the prompt/system_prompt/history the service passes in."""

    def __init__(self):
        self.calls = []

    async def generate_text(self, prompt, system_prompt=None, history=None):
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "history": history}
        )
        return "네, 도와드리겠습니다."

    async def stream_text(self, prompt, system_prompt=None, history=None):
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "history": history}
        )
        for w in "네 도와드리겠습니다".split(" "):
            yield w + " "

    async def analyze_claim_image(self, image_bytes, mime_type, industry=None):
        raise NotImplementedError


class _EmptyRAG:
    def lookup_deterministic_faq(self, message, exclude_keywords=None):
        return None

    async def search_with_store_knowledge(self, session, mall_id, message, top_k=2, industry=None):
        return []

    def assemble_context(self, results, reject_prices=None):
        return ""


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _add_store(session, mall_id="memory_test_mall"):
    store = StoreModel(
        id="store-1",
        mall_id=mall_id,
        store_name="테스트 뷰티몰",
        industry="beauty",
        business_hours="365일 24시간",
        contact_email="cs@test.co.kr",
        policy_config_json='{"max_claim_days":7}',
    )
    session.add(store)
    await session.commit()


@pytest.mark.asyncio
async def test_second_message_receives_prior_turn_as_history(db_session):
    router = _RecordingRouter()
    svc = ChatService(ai_router=router, rag=_EmptyRAG())

    # Turn 1
    sid, reply, intent, _ = await svc.handle_message(
        db_session, None, "cust-1", "사은품 뭐가 있나요?", mall_id="memory_test_mall"
    )
    assert intent == "general_cs"
    # First turn: no prior history
    assert router.calls[0]["history"] == []

    # Turn 2 (same session)
    await svc.handle_message(
        db_session, sid, "cust-1", "그 중에 뭐가 제일 좋아요?", mall_id="memory_test_mall"
    )
    second = router.calls[1]
    # Prior turn is present, oldest first, and the current prompt is NOT duplicated
    assert second["history"] == [
        {"role": "user", "content": "사은품 뭐가 있나요?"},
        {"role": "assistant", "content": "네, 도와드리겠습니다."},
    ]


@pytest.mark.asyncio
async def test_general_cs_gets_store_grounded_system_prompt(db_session):
    router = _RecordingRouter()
    svc = ChatService(ai_router=router, rag=_EmptyRAG())
    await _add_store(db_session)

    # Avoid store_policy_faq / global FAQ keywords so the LLM path runs
    await svc.handle_message(
        db_session, None, "cust-1", "사은품 구성이 어떻게 되나요?", mall_id="memory_test_mall"
    )
    sp = router.calls[0]["system_prompt"]
    assert sp is not None
    assert "테스트 뷰티몰" in sp
    assert "7일" in sp  # claim policy injected from the store record


@pytest.mark.asyncio
async def test_guardrail_corrects_hallucinated_window_in_general_cs(db_session):
    class _HallucinatingRouter(_RecordingRouter):
        async def generate_text(self, prompt, system_prompt=None, history=None):
            await super().generate_text(prompt, system_prompt, history)
            return "반품은 수령 후 3일 이내에만 접수됩니다."

    router = _HallucinatingRouter()
    svc = ChatService(ai_router=router, rag=_EmptyRAG())
    await _add_store(db_session)  # policy max_claim_days=7

    # Wording must not match store_policy_faq patterns (기한/정책) so LLM runs
    _, reply, intent, _ = await svc.handle_message(
        db_session, None, "cust-1", "파손되면 어떻게 보상되나요?", mall_id="memory_test_mall"
    )
    assert intent == "general_cs"
    # The hallucinated 3일 is re-anchored to the store's real 7일 policy
    assert "7일 이내" in reply
    assert "3일 이내" not in reply.split("※")[0]


@pytest.mark.asyncio
async def test_stream_path_also_sends_memory_and_store_prompt(db_session):
    router = _RecordingRouter()
    svc = ChatService(ai_router=router, rag=_EmptyRAG())
    await _add_store(db_session)

    # Prime one prior turn directly (must match mall_id used by stream_chat_response)
    sess = SessionModel(
        id="sess-stream",
        customer_id="cust-1",
        mall_id="memory_test_mall",
        channel="web_widget",
    )
    db_session.add(sess)
    db_session.add(
        MessageModel(id="m1", session_id="sess-stream", role="user", content="이전 질문")
    )
    db_session.add(
        MessageModel(id="m2", session_id="sess-stream", role="assistant", content="이전 답변")
    )
    await db_session.commit()

    tokens = [
        t
        async for t in svc.stream_chat_response(
            db_session, "sess-stream", "cust-1", "스트리밍 질문", mall_id="memory_test_mall"
        )
        if isinstance(t, str)
    ]
    assert tokens
    call = router.calls[0]
    assert call["history"] == [
        {"role": "user", "content": "이전 질문"},
        {"role": "assistant", "content": "이전 답변"},
    ]
    assert "테스트 뷰티몰" in call["system_prompt"]


@pytest.mark.asyncio
async def test_history_loader_orders_and_filters_roles(db_session):
    svc = ChatService(ai_router=_RecordingRouter(), rag=_EmptyRAG())
    sess = SessionModel(id="sess-h", customer_id="c", mall_id="demo_mall", channel="web_widget")
    db_session.add(sess)
    db_session.add(MessageModel(id="a", session_id="sess-h", role="user", content="1"))
    db_session.add(MessageModel(id="b", session_id="sess-h", role="assistant", content="2"))
    db_session.add(MessageModel(id="c", session_id="sess-h", role="system", content="skip"))
    db_session.add(MessageModel(id="d", session_id="sess-h", role="user", content="   "))
    await db_session.commit()

    history = await svc._load_history(db_session, "sess-h")
    assert history == [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "2"},
    ]

    # Excluding the newest user row by id drops only that row
    db_session.add(MessageModel(id="e", session_id="sess-h", role="user", content="현재"))
    await db_session.commit()
    hist2 = await svc._load_history(db_session, "sess-h", exclude_id="e")
    assert hist2[-1] == {"role": "assistant", "content": "2"}
    assert all(h["content"] != "현재" for h in hist2)
