import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_static_widget_served():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/static/chatbot-widget.js")
        assert resp.status_code == 200
        assert "FreshClaimWidgetConfig" in resp.text
        assert "fresh-widget-launcher" in resp.text


@pytest.mark.asyncio
async def test_static_index_html_served():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/static/index.html")
        assert resp.status_code == 200
        assert "챗봇 아틀리에 쇼룸" in resp.text
