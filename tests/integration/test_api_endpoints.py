import io
import pytest
from httpx import ASGITransport, AsyncClient
from app.infrastructure.database.session import init_db
from app.main import app


@pytest.fixture(autouse=True)
async def setup_test_database():
    await init_db()


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert "Fresh Food" in data["service"]
        assert resp.headers.get("X-Correlation-ID") is not None


@pytest.mark.asyncio
async def test_chat_faq_and_cs_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. FAQ lookup (0 tokens)
        faq_resp = await client.post(
            "/api/chat",
            json={"message": "배송비 얼마예요?", "customer_id": "cust-01"},
        )
        assert faq_resp.status_code == 200
        faq_data = faq_resp.json()
        assert "3,000원" in faq_data["message"]
        assert faq_data["intent"] == "faq_deterministic"

        # 2. General CS
        cs_resp = await client.post(
            "/api/chat",
            json={"message": "안녕하세요 반갑습니다", "customer_id": "cust-01"},
        )
        assert cs_resp.status_code == 200
        cs_data = cs_resp.json()
        assert len(cs_data["message"]) > 0


@pytest.mark.asyncio
async def test_chat_sse_stream_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "딸기 보관법 알려주세요", "customer_id": "cust-02"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        text_body = resp.text
        assert "data: " in text_body
        assert "[DONE]" in text_body


@pytest.mark.asyncio
async def test_order_lookup_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/orders/ORD-NORMAL")
        assert resp.status_code == 200
        data = resp.json()
        assert data["order_id"] == "ORD-NORMAL"
        assert data["status"] == "delivered"
        assert len(data["items"]) > 0


@pytest.mark.asyncio
async def test_claim_creation_and_image_analysis_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create claim
        claim_resp = await client.post(
            "/api/claims",
            json={
                "order_id": "ORD-NORMAL",
                "customer_id": "CUST-001",
                "claim_type": "fresh_defect",
                "description": "딸기 상자에 곰팡이가 많이 피어 있습니다.",
            },
        )
        assert claim_resp.status_code == 200
        claim_data = claim_resp.json()
        claim_id = claim_data["claim_id"]
        assert claim_data["status"] == "RECEIVED"

        # 2. Upload valid image
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01" + b"\x00" * 200
        files = {"file": ("strawberry_mold.jpg", io.BytesIO(dummy_jpeg), "image/jpeg")}
        upload_resp = await client.post(f"/api/claims/{claim_id}/images", files=files)
        assert upload_resp.status_code == 200
        result_data = upload_resp.json()

        assert result_data["claim_id"] == claim_id
        # In mock mode, damage is 35% -> FULL_REFUND -> AUTO_APPROVED
        assert result_data["decision"] == "FULL_REFUND"
        assert result_data["status"] == "AUTO_APPROVED"
        assert result_data["refund_amount"] == 24000
        assert "환불" in result_data["customer_message"]

        # 3. Query back claim status
        get_resp = await client.get(f"/api/claims/{claim_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "AUTO_APPROVED"


@pytest.mark.asyncio
async def test_admin_endpoints_protection_and_override():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Unauthorized without key
        unauth_resp = await client.get("/api/admin/claims")
        assert unauth_resp.status_code == 401

        # 2. Authorized with key
        headers = {"X-Admin-Key": "admin-dev-secret-key-change-in-prod"}
        auth_resp = await client.get("/api/admin/claims", headers=headers)
        assert auth_resp.status_code == 200
        assert isinstance(auth_resp.json(), list)
