import pytest
from httpx import ASGITransport, AsyncClient
from app.infrastructure.database.session import init_db
from app.main import app


@pytest.fixture(autouse=True)
async def init_db_fixture():
    await init_db()


@pytest.mark.asyncio
async def test_multitenant_store_registration_and_widget_serving():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register Electronics AS Store
        res1 = await client.post(
            "/api/stores",
            json={
                "store_name": "스마트 가전 A/S 센터",
                "industry": "electronics",
                "mall_id": "smart_home_as",
                "theme_color": "#1E40AF",
            },
        )
        assert res1.status_code == 201
        data1 = res1.json()
        assert data1["mall_id"] == "smart_home_as"
        assert "mall_id=smart_home_as" in data1["embed_script_tag"]

        # 2. Register Fresh Food Store
        res2 = await client.post(
            "/api/stores",
            json={
                "store_name": "프레시 팜 과일몰",
                "industry": "fresh_food",
                "mall_id": "fresh_farm_mall",
                "theme_color": "#2E7D32",
            },
        )
        assert res2.status_code == 201
        data2 = res2.json()
        assert data2["mall_id"] == "fresh_farm_mall"

        # 3. Request customized widget for Electronics Store
        widget1_resp = await client.get("/api/widget/script?mall_id=smart_home_as")
        assert widget1_resp.status_code == 200
        assert "application/javascript" in widget1_resp.headers["content-type"]
        script1_text = widget1_resp.text
        assert "스마트 가전 A/S 센터" in script1_text
        assert "#1E40AF" in script1_text
        assert "A/S 진단 요청" in script1_text

        # 4. Request customized widget for Fresh Food Store
        widget2_resp = await client.get("/api/widget/script?mall_id=fresh_farm_mall")
        assert widget2_resp.status_code == 200
        script2_text = widget2_resp.text
        assert "프레시 팜 과일몰" in script2_text
        assert "#2E7D32" in script2_text
        assert "손상 상품 사진 업로드" in script2_text


@pytest.mark.asyncio
async def test_intelligent_as_troubleshooting_faq():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Electronics AS troubleshooting
        resp = await client.post(
            "/api/chat",
            json={"message": "전자기기 전원불량 해결법 알려줘", "customer_id": "guest_as_user"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "충전 케이블" in data["message"]
        assert "리셋" in data["message"]
        assert "A/S 사진 접수" in data["message"]
