"""Header brand pill: logo when set, store name text when not."""
import io

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.infrastructure.avatar_compress import compress_logo_bytes
from app.infrastructure.database.session import init_db
from app.main import app


@pytest.fixture(autouse=True)
async def init_db_fixture():
    await init_db()


def test_logo_compress_preserves_wide_aspect():
    img = Image.new("RGB", (400, 100), (20, 100, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data, mime = compress_logo_bytes(buf.getvalue(), max_edge=96)
    out = Image.open(io.BytesIO(data))
    assert max(out.size) <= 96
    assert out.size[0] > out.size[1]  # still wider than tall


@pytest.mark.asyncio
async def test_widget_falls_back_to_badge_text_without_logo():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/stores",
            json={
                "store_name": "로고없는몰",
                "industry": "beauty",
                "mall_id": "no_logo_mall",
                "brand_badge": "루이셀",
            },
        )
        assert res.status_code == 201
        assert not res.json().get("brand_logo_url")

        script = await client.get("/api/widget/script", params={"mall_id": "no_logo_mall"})
        assert script.status_code == 200
        assert "fresh-brand-pill" in script.text
        assert "루이셀" in script.text
        assert 'class="fresh-brand-pill has-logo"' not in script.text
        assert 'class="fresh-brand-pill">루이셀</span>' in script.text


@pytest.mark.asyncio
async def test_brand_logo_upload_renders_img():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/stores",
            json={
                "store_name": "로고몰",
                "industry": "beauty",
                "mall_id": "with_logo_mall",
                "brand_badge": "루이셀",
            },
        )
        img = Image.new("RGB", (200, 80), (226, 40, 120))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        up = await client.post(
            "/api/stores/with_logo_mall/brand-logo",
            files={"file": ("logo.png", buf.getvalue(), "image/png")},
        )
        assert up.status_code == 200
        assert up.json().get("brand_logo_url", "").startswith("data:image/")

        script = await client.get("/api/widget/script", params={"mall_id": "with_logo_mall"})
        assert script.status_code == 200
        assert "has-logo" in script.text
        assert "fresh-brand-logo-img" in script.text
