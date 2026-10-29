"""Store RAG must not mix default docs across industries."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.models import Base, StoreKnowledgeModel, StoreModel
from app.infrastructure.rag.engine import RAGEngine


@pytest.mark.asyncio
async def test_store_with_knowledge_skips_default_docs():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        session.add(
            StoreModel(
                id="s1",
                mall_id="beauty_iso",
                store_name="뷰티몰",
                industry="beauty",
            )
        )
        session.add(
            StoreKnowledgeModel(
                id="k1",
                mall_id="beauty_iso",
                doc_type="product",
                title="시카 크림",
                content="민감성 진정 크림 보습",
                price=20000,
            )
        )
        await session.commit()

        rag = RAGEngine()
        hits = await rag.search_with_store_knowledge(
            session, "beauty_iso", "민감성 보습", top_k=5, industry="beauty"
        )
        titles = [h.document.title for h in hits]
        assert "시카 크림" in titles
        assert not any("딸기" in t for t in titles)

    await engine.dispose()


@pytest.mark.asyncio
async def test_empty_store_only_gets_same_industry_defaults():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        session.add(
            StoreModel(
                id="s2",
                mall_id="fresh_empty",
                store_name="신선몰",
                industry="fresh_food",
            )
        )
        await session.commit()

        rag = RAGEngine()
        hits = await rag.search_with_store_knowledge(
            session, "fresh_empty", "딸기 보관", top_k=5, industry="fresh_food"
        )
        assert any("딸기" in h.document.title for h in hits)

        beauty_empty = await rag.search_with_store_knowledge(
            session, "fresh_empty", "딸기 보관", top_k=5, industry="beauty"
        )
        # Same mall has no beauty-tagged defaults → no strawberry for beauty industry filter
        assert all(h.document.metadata.get("industry") != "fresh_food" for h in beauty_empty) or len(beauty_empty) == 0

    await engine.dispose()
