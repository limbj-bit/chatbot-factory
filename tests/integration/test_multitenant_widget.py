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

        # 5. Register Beauty Store
        res3 = await client.post(
            "/api/stores",
            json={
                "store_name": "벨라 뷰티 코스메틱",
                "industry": "beauty",
                "mall_id": "bella_beauty",
            },
        )
        assert res3.status_code == 201
        widget3_resp = await client.get("/api/widget/script?mall_id=bella_beauty")
        assert widget3_resp.status_code == 200
        script3_text = widget3_resp.text
        assert "벨라 뷰티 코스메틱" in script3_text
        assert "#EC4899" in script3_text
        assert "용기 누유/파손" in script3_text


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

        # Beauty skin trouble guidance FAQ (neutral, no guaranteed refund promise)
        beauty_resp = await client.post(
            "/api/chat",
            json={"message": "화장품 쓰고 피부트러블 났는데 환불 되나요?", "customer_id": "guest_beauty_user"},
        )
        assert beauty_resp.status_code == 200
        bdata = beauty_resp.json()
        assert "사용을 중단" in bdata["message"]
        assert "피부과 전문의" in bdata["message"]
        assert "100% 전액 환불" not in bdata["message"]


@pytest.mark.asyncio
async def test_widget_trial_warning_expiry_and_remote_extension():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register store with 2 days left (pre-expiration warning)
        res_warn = await client.post(
            "/api/stores",
            json={
                "store_name": "루미에르 뷰티 (체험 2일 남음)",
                "industry": "beauty",
                "mall_id": "lumiere_warn",
                "trial_days": 2,
            },
        )
        assert res_warn.status_code == 201
        warn_script = (await client.get("/api/widget/script?mall_id=lumiere_warn")).text
        assert "expiryWarning: true" in warn_script
        assert "isExpired: false" in warn_script
        assert "사용기한 만료 임박" in warn_script

        # 2. Register store with 0 days (expired)
        res_exp = await client.post(
            "/api/stores",
            json={
                "store_name": "루미에르 뷰티 (체험 만료)",
                "industry": "beauty",
                "mall_id": "lumiere_expired",
                "trial_days": 0,
            },
        )
        assert res_exp.status_code == 201
        exp_script = (await client.get("/api/widget/script?mall_id=lumiere_expired")).text
        assert "isExpired: true" in exp_script
        assert "기간 만료 안내" in exp_script
        assert "사용기한이 만료되어 입력할 수 없습니다" in exp_script

        # 3. Attempt to extend subscription without Admin Key -> must be blocked (401)
        unauth_patch = await client.patch(
            "/api/stores/lumiere_expired/subscription",
            json={"extend_days": 30, "plan_type": "active"},
        )
        assert unauth_patch.status_code == 401

        # 4. Extend subscription by 30 days remotely via Admin Key
        admin_headers = {"X-Admin-Key": "admin-dev-secret-key-change-in-prod"}
        patch_res = await client.patch(
            "/api/stores/lumiere_expired/subscription",
            json={"extend_days": 30, "plan_type": "active"},
            headers=admin_headers,
        )
        assert patch_res.status_code == 200
        patch_data = patch_res.json()
        assert patch_data["is_expired"] is False
        assert patch_data["remaining_days"] == 30

        # 4. Widget script immediately reflects active state without changing script tag
        restored_script = (await client.get("/api/widget/script?mall_id=lumiere_expired")).text
        assert "isExpired: false" in restored_script
        assert "expiryWarning: false" in restored_script
