import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

CACHEABLE = "public, max-age=600, stale-while-revalidate=86400"
UNCACHED = "no-cache, no-store, must-revalidate, max-age=0"


async def _get(params: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/api/widget/script", params=params)


@pytest.mark.asyncio
async def test_plain_embed_script_is_cacheable():
    resp = await _get({"mall_id": "cache_plain_mall"})
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == CACHEABLE
    assert resp.headers.get("vary") == "Accept-Encoding"


@pytest.mark.asyncio
async def test_preview_script_stays_uncached():
    resp = await _get({"mall_id": "cache_preview_mall", "preview_bot_name": "루나봇"})
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == UNCACHED


@pytest.mark.asyncio
async def test_script_rate_limited_per_store():
    """60/min per mall_id: 61st call gets 429, other stores unaffected."""
    mall = "cache_ratelimit_mall"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(60):
            ok = await client.get("/api/widget/script", params={"mall_id": mall})
            assert ok.status_code == 200
        blocked = await client.get("/api/widget/script", params={"mall_id": mall})
        other = await client.get(
            "/api/widget/script", params={"mall_id": "cache_other_mall"}
        )

    assert blocked.status_code == 429
    assert other.status_code == 200
