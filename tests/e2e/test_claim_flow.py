import io
import pytest
from httpx import ASGITransport, AsyncClient
from app.infrastructure.database.session import init_db
from app.main import app


@pytest.fixture(autouse=True)
async def init_db_fixture():
    await init_db()


@pytest.mark.asyncio
async def test_e2e_complete_auto_approval_flow():
    """Scenario 1: End-to-end happy path for strawberry mold claim leading to auto-approval."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Customer initial inquiry
        chat_res = await client.post(
            "/api/chat",
            json={"message": "딸기가 다 물러서 왔어요", "customer_id": "cust-happy-01"},
        )
        assert chat_res.status_code == 200
        session_id = chat_res.json()["session_id"]

        # Step 2: Customer checks order
        order_res = await client.get("/api/orders/ORD-NORMAL")
        assert order_res.status_code == 200
        order_data = order_res.json()
        assert order_data["status"] == "delivered"
        assert order_data["total_amount"] == 24000

        # Step 3: Customer creates claim
        create_res = await client.post(
            "/api/claims",
            json={
                "order_id": "ORD-NORMAL",
                "customer_id": "cust-happy-01",
                "claim_type": "fresh_defect",
                "description": "설향 딸기 상자에 곰팡이가 피어 있고 과육이 다 짓물렀습니다.",
            },
        )
        assert create_res.status_code == 200
        claim_id = create_res.json()["claim_id"]
        assert create_res.json()["status"] == "RECEIVED"

        # Step 4: Customer uploads photo
        # Valid JPEG header + content
        dummy_jpeg = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"
            + b"\x00" * 300
            + b"FRESH_CLAIM_NORMAL_IMAGE"
        )
        files = {"file": ("mold_strawberry.jpg", io.BytesIO(dummy_jpeg), "image/jpeg")}
        upload_res = await client.post(f"/api/claims/{claim_id}/images", files=files)
        assert upload_res.status_code == 200
        upload_data = upload_res.json()

        # Step 5: Verification of Deterministic Decision
        assert upload_data["status"] == "AUTO_APPROVED"
        assert upload_data["decision"] == "FULL_REFUND"
        assert upload_data["refund_amount"] == 24000
        assert upload_data["observation"]["damage_ratio"] >= 30
        assert upload_data["observation"]["defect_type"] == "mold"

        # Step 6: Verify final claim state
        final_claim = await client.get(f"/api/claims/{claim_id}")
        assert final_claim.status_code == 200
        assert final_claim.json()["status"] == "AUTO_APPROVED"
        assert final_claim.json()["refund_amount"] == 24000


@pytest.mark.asyncio
async def test_e2e_expired_claim_window_flow():
    """Scenario 2: Order delivered > 2 days ago should be rejected deterministically."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create claim for expired order (delivered 4 days ago)
        create_res = await client.post(
            "/api/claims",
            json={
                "order_id": "ORD-EXPIRED",
                "customer_id": "cust-late-02",
                "claim_type": "fresh_defect",
                "description": "토마토가 상했습니다.",
            },
        )
        claim_id = create_res.json()["claim_id"]

        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01" + b"\x00" * 150
        files = {"file": ("tomato.jpg", io.BytesIO(dummy_jpeg), "image/jpeg")}
        upload_res = await client.post(f"/api/claims/{claim_id}/images", files=files)
        assert upload_res.status_code == 200
        data = upload_res.json()

        assert data["decision"] == "REJECT"
        assert data["reason_code"] == "EXPIRED_WINDOW"
        assert data["status"] == "REJECTED"
        assert "48시간" in data["customer_message"] or "2일" in data["customer_message"]


@pytest.mark.asyncio
async def test_e2e_blurry_image_quality_gate_flow():
    """Scenario 3: Blurry photo triggers RETAKE_IMAGE instead of making a wrong refund decision."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post(
            "/api/claims",
            json={
                "order_id": "ORD-NORMAL",
                "customer_id": "cust-blur-03",
                "claim_type": "fresh_defect",
                "description": "과일 확인해 주세요.",
            },
        )
        claim_id = create_res.json()["claim_id"]

        # Blurry image trigger in mock provider
        blurry_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01" + b"BLURRY_TRIGGER" + b"\x00" * 100
        files = {"file": ("blurry.jpg", io.BytesIO(blurry_jpeg), "image/jpeg")}
        upload_res = await client.post(f"/api/claims/{claim_id}/images", files=files)
        assert upload_res.status_code == 200
        data = upload_res.json()

        assert data["decision"] == "RETAKE_IMAGE"
        assert data["reason_code"] == "POOR_IMAGE_QUALITY"
        assert data["status"] == "IMAGE_RETAKE_REQUIRED"
        assert "다시 촬영" in data["customer_message"]


@pytest.mark.asyncio
async def test_e2e_duplicate_image_fraud_to_admin_review():
    """Scenario 4: Duplicate image submission detected, routed to MANUAL_REVIEW, and approved by Admin."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        identical_image = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01" + b"IDENTICAL_FRAUD_TRIGGER" + b"\x00" * 200

        # First claim with this image
        res1 = await client.post(
            "/api/claims",
            json={"order_id": "ORD-NORMAL", "customer_id": "cust-user-a", "claim_type": "fresh_defect", "description": "1차 접수"},
        )
        claim1_id = res1.json()["claim_id"]
        await client.post(f"/api/claims/{claim1_id}/images", files={"file": ("img1.jpg", io.BytesIO(identical_image), "image/jpeg")})

        # Second claim with the EXACT same image content (duplicate hash)
        res2 = await client.post(
            "/api/claims",
            json={"order_id": "ORD-NORMAL", "customer_id": "cust-user-b", "claim_type": "fresh_defect", "description": "2차 동일 이미지 접수"},
        )
        claim2_id = res2.json()["claim_id"]
        upload2 = await client.post(f"/api/claims/{claim2_id}/images", files={"file": ("img2.jpg", io.BytesIO(identical_image), "image/jpeg")})
        assert upload2.status_code == 200
        data2 = upload2.json()

        # Must NOT auto-approve! Routed to MANUAL_REVIEW due to SUSPICIOUS_CLAIM
        assert data2["decision"] == "MANUAL_REVIEW"
        assert data2["reason_code"] == "SUSPICIOUS_CLAIM"
        assert data2["status"] == "MANUAL_REVIEW"
        assert data2["requires_manual_review"] is True

        # Admin inspects claims queue
        admin_headers = {"X-Admin-Key": "admin-dev-secret-key-change-in-prod"}
        claims_list_resp = await client.get("/api/admin/claims", headers=admin_headers)
        assert claims_list_resp.status_code == 200
        pending_list = claims_list_resp.json()
        assert any(c["claim_id"] == claim2_id for c in pending_list)

        # Admin overrides and approves partial refund (10,000 KRW)
        approve_resp = await client.post(
            f"/api/admin/claims/{claim2_id}/approve",
            json={"refund_amount": 10000, "reason": "고객 소명 확인 후 수동 승인"},
            headers=admin_headers,
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["approved"] is True

        # Claim status is now COMPLETED with 10,000 KRW refund
        check_res = await client.get(f"/api/claims/{claim2_id}")
        assert check_res.json()["status"] == "COMPLETED"
        assert check_res.json()["refund_amount"] == 10000
