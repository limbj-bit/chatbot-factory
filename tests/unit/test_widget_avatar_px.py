"""Launcher avatar_px from widget_layout / preview query."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.database.session import init_db
from app.main import app


@pytest.fixture(autouse=True)
async def init_db_fixture():
    await init_db()


@pytest.mark.asyncio
async def test_preview_avatar_px_changes_ring_css():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r64 = await client.get(
            "/api/widget/script",
            params={"mall_id": "showroom_preview", "preview_avatar_px": 64},
        )
        r88 = await client.get(
            "/api/widget/script",
            params={"mall_id": "showroom_preview", "preview_avatar_px": 88},
        )
        assert r64.status_code == 200 and r88.status_code == 200
        assert "width: 64px; height: 64px" in r64.text
        assert "width: 88px; height: 88px" in r88.text


@pytest.mark.asyncio
async def test_store_widget_layout_includes_avatar_px():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/stores",
            json={
                "store_name": "크기몰",
                "industry": "beauty",
                "mall_id": "avatar_px_mall",
                "policy_config": {
                    "widget_layout": {
                        "pos": "bottom_right",
                        "bottom_px": 30,
                        "side_px": 20,
                        "avatar_px": 88,
                    }
                },
            },
        )
        assert res.status_code == 201
        body = res.json()
        assert body.get("widget_layout", {}).get("avatar_px") == 88

        script = await client.get("/api/widget/script", params={"mall_id": "avatar_px_mall"})
        assert script.status_code == 200
        assert "width: 88px; height: 88px" in script.text
