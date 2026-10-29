"""Widget preview should keep saved custom avatars when loading a store."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.database.session import init_db
from app.main import app


@pytest.fixture(autouse=True)
async def init_db_fixture():
    await init_db()


@pytest.mark.asyncio
async def test_widget_script_avatar_preview_rules():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Valid tiny 1x1 PNG so create/widget paths keep the avatar as-is.
        avatar = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        res = await client.post(
            "/api/stores",
            json={
                "store_name": "아바타몰",
                "industry": "beauty",
                "mall_id": "avatar_preview_mall",
                "bot_name": "루나봇",
                "bot_icon_style": "custom_upload",
                "bot_avatar_url": avatar,
                "welcome_message": "저장된 환영",
            },
        )
        assert res.status_code == 201

        r1 = await client.get(
            "/api/widget/script",
            params={
                "mall_id": "avatar_preview_mall",
                "preview_icon": "custom_upload",
                "preview_bot_name": "루나봇",
            },
        )
        assert r1.status_code == 200
        assert avatar in r1.text

        preview_av = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        r2 = await client.get(
            "/api/widget/script",
            params={
                "mall_id": "avatar_preview_mall",
                "preview_icon": "preset_beauty_model",
                "preview_avatar_url": preview_av,
            },
        )
        assert preview_av in r2.text

        r3 = await client.get(
            "/api/widget/script",
            params={
                "mall_id": "avatar_preview_mall",
                "preview_icon": "flaticon_cute_robot",
            },
        )
        assert avatar not in r3.text
