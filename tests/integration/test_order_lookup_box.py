import pytest
from httpx import ASGITransport, AsyncClient
from app.infrastructure.database.session import init_db
from app.main import app


@pytest.fixture(autouse=True)
async def init_db_fixture():
    await init_db()


@pytest.mark.asyncio
async def test_order_lookup_box_shown_only_when_commerce_connected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Showroom preview with commerce platform selected -> box config enabled
        res_on = await client.get("/api/widget/script?mall_id=showroom_preview&preview_commerce=cafe24")
        assert res_on.status_code == 200
        assert 'commercePlatform: "cafe24"' in res_on.text
        assert "카페24 실시간 연동" in res_on.text
        assert "dyn-order-input" in res_on.text

        # 2. No commerce platform -> box disabled (platform "none")
        res_off = await client.get("/api/widget/script?mall_id=showroom_preview")
        assert res_off.status_code == 200
        assert 'commercePlatform: "none"' in res_off.text

        # 3. Issued store with saved commerce_api -> box enabled from DB
        res_store = await client.post(
            "/api/stores",
            json={
                "store_name": "주문박스 테스트몰",
                "industry": "fashion",
                "mall_id": "order_box_mall",
                "policy_config": {
                    "commerce_api": {"platform": "naver_smartstore", "store_uid": "abc", "client_key": "k"}
                },
            },
        )
        assert res_store.status_code == 201
        res_saved = await client.get("/api/widget/script?mall_id=order_box_mall")
        assert 'commercePlatform: "naver_smartstore"' in res_saved.text
        assert "스마트스토어 실시간 연동" in res_saved.text
