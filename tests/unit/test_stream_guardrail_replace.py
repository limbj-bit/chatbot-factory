"""Streaming claim-window guardrail emits a replace event for the widget."""
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.chat_service import ChatService
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.database.models import Base, StoreModel


class _HallucinateStreamRouter(AIProviderPort):
    async def generate_text(self, prompt, system_prompt=None, history=None):
        return "x"

    async def stream_text(self, prompt, system_prompt=None, history=None):
        for part in ["반품은 ", "수령 후 ", "3일 이내", "에만 가능합니다."]:
            yield part

    async def analyze_claim_image(self, image_bytes, mime_type, industry=None):
        raise NotImplementedError


class _EmptyRAG:
    def lookup_deterministic_faq(self, message, exclude_keywords=None):
        return None

    async def search_with_store_knowledge(self, session, mall_id, message, top_k=2):
        return []

    def assemble_context(self, results):
        return ""


@pytest.mark.asyncio
async def test_stream_emits_replace_when_claim_window_wrong():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        session.add(
            StoreModel(
                id="s1",
                mall_id="guard_mall",
                store_name="가드몰",
                industry="beauty",
                policy_config_json=json.dumps({"claim_policy": {"max_claim_days": 7}}),
            )
        )
        await session.commit()

        svc = ChatService(ai_router=_HallucinateStreamRouter(), rag=_EmptyRAG())
        events = [
            e
            async for e in svc.stream_chat_response(
                session, None, "c1", "파손되면 어떻게 보상되나요?", mall_id="guard_mall"
            )
        ]

    tokens = [e for e in events if isinstance(e, str)]
    replaces = [e for e in events if isinstance(e, dict) and "__stream_replace__" in e]
    assert "".join(tokens)  # streamed raw first
    assert len(replaces) == 1
    fixed = replaces[0]["__stream_replace__"]
    assert "7일 이내" in fixed
    assert "3일 이내" not in fixed.split("※")[0]

    await engine.dispose()
