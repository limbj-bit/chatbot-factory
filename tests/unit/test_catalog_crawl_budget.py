"""Catalog crawl: category expand past thin sitemaps + URL cache resume."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.store_service import store_service
from app.infrastructure.database.models import Base, StoreModel
from app.schemas.store import StoreCatalogCrawlRequest, StoreKnowledgeResponse


def _sitemap_with_n_products(n: int, categories: int = 0) -> str:
    locs = [
        f"<url><loc>https://example.com/product/item-{i}/{1000 + i}/</loc></url>"
        for i in range(n)
    ]
    locs += [
        f"<url><loc>https://example.com/category/cat-{i}/{200 + i}/</loc></url>"
        for i in range(categories)
    ]
    return (
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(locs)
        + "</urlset>"
    )


async def _fake_learn(session, mall_id, req):
    return StoreKnowledgeResponse(
        id="k-" + (req.url[-12:].replace("/", "")),
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


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    store_service._catalog_url_cache.clear()
    yield
    store_service._catalog_url_cache.clear()


@pytest.mark.asyncio
async def test_sitemap_with_categories_runs_expand_not_thin_deep():
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

        deep = AsyncMock(side_effect=AssertionError("thin deep crawl must be skipped"))

        async def _expand(category_urls, seed_urls, **kwargs):
            extra = [
                "https://example.com/product/extra-a/9001/",
                "https://example.com/product/extra-b/9002/",
            ]
            return seed_urls + extra, {
                "categories_visited": len(category_urls),
                "pages_fetched": 2,
                "product_urls": len(seed_urls) + 2,
            }

        req = StoreCatalogCrawlRequest(
            url="https://example.com/sitemap.xml",
            max_products=3,
            offset=0,
            force_refresh=False,
            raw_html_override=_sitemap_with_n_products(20, categories=3),
        )

        with patch.object(store_service, "_deep_crawl_product_urls", deep), patch.object(
            store_service, "_expand_catalog_from_categories", AsyncMock(side_effect=_expand)
        ), patch.object(
            store_service, "crawl_and_learn_url", AsyncMock(side_effect=_fake_learn)
        ):
            resp = await store_service.crawl_store_catalog(session, "catalog_test_mall", req)

        deep.assert_not_called()
        assert resp.total_products == 22  # 20 sitemap + 2 expanded
        assert resp.learned == 3
        assert resp.has_more is True
        assert resp.next_offset > 0
        assert "카테고리" in (resp.notes or "") or "발견" in (resp.notes or "")

    await engine.dispose()


@pytest.mark.asyncio
async def test_offset_resume_uses_cache_without_rediscovery():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        session.add(
            StoreModel(
                id="s-cache",
                mall_id="cache_mall",
                store_name="캐시몰",
                industry="beauty",
            )
        )
        await session.commit()

        async def _expand(category_urls, seed_urls, **kwargs):
            return seed_urls, {
                "categories_visited": 0,
                "pages_fetched": 0,
                "product_urls": len(seed_urls),
            }

        expand = AsyncMock(side_effect=_expand)
        req0 = StoreCatalogCrawlRequest(
            url="https://example.com/sitemap.xml",
            max_products=2,
            offset=0,
            force_refresh=False,
            raw_html_override=_sitemap_with_n_products(10, categories=1),
        )
        with patch.object(
            store_service, "_expand_catalog_from_categories", expand
        ), patch.object(
            store_service, "crawl_and_learn_url", AsyncMock(side_effect=_fake_learn)
        ):
            first = await store_service.crawl_store_catalog(session, "cache_mall", req0)
            assert first.has_more is True
            assert expand.await_count == 1

            req1 = StoreCatalogCrawlRequest(
                url="https://example.com/sitemap.xml",
                max_products=2,
                offset=first.next_offset,
                force_refresh=False,
            )
            second = await store_service.crawl_store_catalog(session, "cache_mall", req1)

        assert expand.await_count == 1  # no rediscovery
        assert second.total_products == first.total_products
        assert second.next_offset > first.next_offset or not second.has_more

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

        html = "<html><body><a href='/about'>about</a></body></html>"
        req = StoreCatalogCrawlRequest(
            url="https://example.com/",
            max_products=2,
            offset=0,
            force_refresh=False,
            raw_html_override=html,
        )

        with patch.object(
            store_service, "_deep_crawl_product_urls", AsyncMock(side_effect=_deep)
        ), patch.object(
            store_service, "crawl_and_learn_url", AsyncMock(side_effect=_fake_learn)
        ):
            resp = await store_service.crawl_store_catalog(session, "thin_mall", req)

        assert resp.total_products >= 3
        assert resp.learned == 2

    await engine.dispose()


def test_normalize_product_url_collapses_cafe24_variants():
    a = store_service._normalize_product_url(
        "https://Shop.Example.com/product/rose-serum/12345/"
    )
    b = store_service._normalize_product_url(
        "https://shop.example.com/product/other-slug/12345"
    )
    c = store_service._normalize_product_url(
        "https://shop.example.com/product/detail.html?product_no=12345"
    )
    assert a == b == c
