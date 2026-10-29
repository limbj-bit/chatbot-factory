"""Showroom widget must still render when store ORM lookup raises."""
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_widget_script_survives_store_lookup_failure(monkeypatch):
    async def _boom(*_a, **_k):
        raise RuntimeError("no such column: brand_logo_url")

    monkeypatch.setattr(
        "app.api.widget.store_service.get_store_by_mall_id",
        _boom,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/widget/script",
            params={
                "mall_id": "showroom_preview",
                "preview_icon": "flaticon_cute_robot",
                "preview_template": "cosraw_grid",
            },
        )
    assert res.status_code == 200
    assert "CHATBOT_FACTORY_SVGS" in res.text
    assert "fresh-widget-launcher" in res.text
