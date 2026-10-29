"""Catalog crawl: skip deep crawl when sitemap already has enough product URLs."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.store_service import store_service
from app.infrastructure.database.models import Base, StoreModel
from app.schemas.store import StoreCatalogCrawlRequest


def _sitemap_with_n_products(n: int) -> str:
    locs = [
        f"<url><loc>https://example.com/product/detail.html?product_no={i}</loc></url>"
        for i in range(n)
    ]
    return (
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(locs)
        + "</urlset>"
    )


@pytest.mark.asyncio
async def test_sitemap_with_enough_urls_skips_deep_crawl():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        session.add(
            StoreModel(
                id="s-cat",
                mall_id="catalog_test_mall",
                store_name="카탈로그몰",
                industry="beauty",
            )
        )
        await session.commit()

        deep = AsyncMock(side_effect=AssertionError("deep crawl must be skipped"))
        learn = AsyncMock(
            side_effect=lambda *_a, **_k: MagicMock(
                id="k1",
                mall_id="catalog_test_mall",
                doc_type="crawled_url",
                title="샘플",
                content="본문",
                source_url="https://example.com/product/detail.html?product_no=0",
                price=1000,
                purchase_url="https://example.com/product/detail.html?product_no=0",
                image_url=None,
                tags=None,
                created_at="2026-01-01T00:00:00+00:00",
            )
        )

        # crawl_and_learn_url returns StoreKnowledgeResponse-like object
        from app.schemas.store import StoreKnowledgeResponse
        from datetime import datetime, timezone

        async def _fake_learn(session, mall_id, req):
            return StoreKnowledgeResponse(
                id="k-" + req.url[-8:],
                mall_id=mall_id,
                doc_type="crawled_url",
                title="상품",
                content="설명",
                source_url=req.url,
                price=1000,
                purchase_url=req.url,
                image_url=None,
                tags=None,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        req = StoreCatalogCrawlRequest(
            url="https://example.com/sitemap.xml",
            max_products=3,
            offset=0,
            force_refresh=True,
            raw_html_override=_sitemap_with_n_products(20),
        )

        with patch.object(store_service, "_deep_crawl_product_urls", deep), patch.object(
            store_service, "crawl_and_learn_url", AsyncMock(side_effect=_fake_learn)
        ):
            resp = await store_service.crawl_store_catalog(session, "catalog_test_mall", req)

        deep.assert_not_called()
        assert resp.total_products == 20
        assert resp.learned == 3
        assert resp.has_more is True
        assert "다음 배치" in (resp.notes or "") or "배치" in (resp.notes or "")

    await engine.dispose()


@pytest.mark.asyncio
async def test_thin_discovery_calls_deep_crawl():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        session.add(
            StoreModel(
                id="s-thin",
                mall_id="thin_mall",
                store_name="씬몰",
                industry="beauty",
            )
        )
        await session.commit()

        async def _deep(seed_url, urls, **kwargs):
            return urls + [
                "https://example.com/product/detail.html?product_no=99",
                "https://example.com/product/detail.html?product_no=98",
                "https://example.com/product/detail.html?product_no=97",
            ]

        from app.schemas.store import StoreKnowledgeResponse
        from datetime import datetime, timezone

        async def _fake_learn(session, mall_id, req):
            return StoreKnowledgeResponse(
                id="k2",
                mall_id=mall_id,
                doc_type="crawled_url",
                title="상품",
                content="설명",
                source_url=req.url,
                price=1,
                purchase_url=req.url,
                image_url=None,
                tags=None,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        # Non-sitemap listing HTML with no product links → thin → deep crawl
        html = "<html><body><a href='/about'>about</a></body></html>"
        req = StoreCatalogCrawlRequest(
            url="https://example.com/",
            max_products=2,
            offset=0,
            force_refresh=True,
            raw_html_override=html,
        )

        with patch.object(store_service, "_deep_crawl_product_urls", AsyncMock(side_effect=_deep)), patch.object(
            store_service, "crawl_and_learn_url", AsyncMock(side_effect=_fake_learn)
        ):
            resp = await store_service.crawl_store_catalog(session, "thin_mall", req)

        assert resp.total_products >= 3
        assert resp.learned == 2

    await engine.dispose()
