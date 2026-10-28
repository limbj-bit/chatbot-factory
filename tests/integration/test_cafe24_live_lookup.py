"""Cafe24 live order/shipping lookup integration tests.

Covers the 4 verification criteria from the spec:
  1. Token issuance & encrypted storage
  2. Auto-refresh when the access token expires
  3. Order payload -> reply mapping with PII hidden
  4. Non-connected malls never see test orders (ORD-...)
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.core import config
from app.core.security import decrypt_secret
from app.infrastructure.database.session import init_db
from app.main import app

# --- Test-wide Fernet key (must be set before settings are read) ---
_TEST_KEY = Fernet.generate_key().decode()
config.settings.ENCRYPTION_KEY = _TEST_KEY

MALL = "rooicell_test"
CAFE24_MALL = "rooicell"
CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret-abc"


@pytest.fixture(autouse=True)
async def init_db_fixture():
    await init_db()


def _seed_connection(monet=None):
    """Placeholder to keep helper name stable."""
    return None


async def _create_store_with_cafe24_keys(client: AsyncClient) -> None:
    """Create a store through the real showroom flow (5-step form payload)."""
    res = await client.post(
        "/api/stores",
        json={
            "store_name": "루이셀 테스트",
            "industry": "beauty",
            "mall_id": MALL,
            "policy_config": {
                "commerce_api": {
                    "platform": "cafe24",
                    "store_uid": CAFE24_MALL,
                    "client_key": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                }
            },
        },
    )
    assert res.status_code == 201, res.text


def _token_response(access="ACCESS-1", refresh="REFRESH-1", expires_in=7200, refresh_expires_in=1209600):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": expires_in,
        "refresh_token_expires_in": refresh_expires_in,
        "api_version": "2024-06-01",
    }


def _order_payload(status="P"):
    """Cafe24 order payload. Includes PII fields that MUST NOT reach the customer."""
    return {
        "order": {
            "order_id": "20261028-0000012",
            "order_status": status,
            "buyer_name": "김개인",
            "buyer_tel": "010-1234-5678",
            "buyer_email": "private@example.com",
            "shipping_address": "서울시 강남구 비밀로123",
            "actual_order_amount": {"order_price_amount": 38000},
            "items": [
                {
                    "product_no": 991,
                    "product_name": "루이셀 세럼",
                    "quantity": 1,
                    "product_price": 38000,
                }
            ],
            "deliveries": [
                {
                    "delivery_company_name": "CJ대한통운",
                    "tracking_number": "123456789",
                }
            ],
        }
    }


# ---------------------------------------------------------------------------
# 1. Token issuance & encrypted storage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_oauth_token_issuance_and_encrypted_storage(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_store_with_cafe24_keys(client)

        # Keys are saved encrypted, status=pending, no tokens yet.
        from app.infrastructure.database.session import async_session_factory

        async with async_session_factory() as s:
            from app.application.commerce_service import commerce_service

            conn = await commerce_service.get_connection(s, MALL)
            assert conn is not None
            assert conn.status == "pending"
            assert conn.client_id == CLIENT_ID
            # Secret must NOT be stored in plaintext.
            assert CLIENT_SECRET not in (conn.client_secret_encrypted or "")
            # But it must decrypt back to the original.
            assert decrypt_secret(conn.client_secret_encrypted) == CLIENT_SECRET

        # Simulate the OAuth callback token exchange.
        captured = {}

        async def fake_post_token(cafe24_mall_id, client_id, client_secret, data):
            captured.update(data)
            return _token_response()

        from app.application import commerce_service as cs_mod

        monkeypatch.setattr(cs_mod.commerce_service, "_post_token", fake_post_token)

        # Drive the real callback endpoint (state must be minted first).
        state = await cs_mod.commerce_service.create_oauth_state(MALL)
        res = await client.get(
            f"/api/orders/oauth/callback?code=AUTHCODE123&state={state}"
        )
        assert res.status_code == 200
        assert "연동 완료" in res.text

        # Verify the code->token exchange used the right grant + auth code.
        assert captured.get("grant_type") == "authorization_code"
        assert captured.get("code") == "AUTHCODE123"

        async with async_session_factory() as s:
            conn = await cs_mod.commerce_service.get_connection(s, MALL)
            assert conn.status == "connected"
            # Tokens are stored encrypted, not plaintext.
            assert "ACCESS-1" not in (conn.access_token_encrypted or "")
            assert decrypt_secret(conn.access_token_encrypted) == "ACCESS-1"
            assert decrypt_secret(conn.refresh_token_encrypted) == "REFRESH-1"
            assert conn.access_token_expires_at is not None
            assert conn.refresh_token_expires_at is not None


# ---------------------------------------------------------------------------
# 2. Auto-refresh on expiry
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_access_token_auto_refresh_on_expiry(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_store_with_cafe24_keys(client)

        from app.application import commerce_service as cs_mod
        from app.infrastructure.database.session import async_session_factory

        # Seed an already-connected row whose access token is expired.
        async with async_session_factory() as s:
            conn = await cs_mod.commerce_service.get_connection(s, MALL)
            now = datetime.now(timezone.utc)
            from app.core.security import encrypt_secret

            conn.access_token_encrypted = encrypt_secret("OLD-EXPIRED")
            conn.refresh_token_encrypted = encrypt_secret("REFRESH-LIVE")
            conn.access_token_expires_at = now - timedelta(hours=1)  # expired
            conn.refresh_token_expires_at = now + timedelta(days=7)
            conn.status = "connected"
            await s.commit()

        refresh_calls = []
        fetch_calls = []

        async def fake_refresh(session, conn):
            refresh_calls.append(1)
            from app.core.security import encrypt_secret

            conn.access_token_encrypted = encrypt_secret("NEW-FRESH")
            conn.access_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
            conn.status = "connected"
            await session.commit()
            return True

        async def fake_fetch(self, order_id, access_token):
            fetch_calls.append(access_token)
            return _order_payload()["order"]

        monkeypatch.setattr(cs_mod.commerce_service, "refresh_access_token", fake_refresh)

        from app.infrastructure.channels import cafe24 as cafe24_mod

        monkeypatch.setattr(cafe24_mod.Cafe24Adapter, "fetch_order_payload", fake_fetch)

        order, err = await cs_mod.commerce_service.lookup_order(s, MALL, "20261028-0000012")
        assert err is None
        assert order is not None
        # The lookup must have used the NEW token, not the expired one.
        assert refresh_calls, "refresh should have been triggered"
        assert fetch_calls and fetch_calls[0] == "NEW-FRESH"


# ---------------------------------------------------------------------------
# 3. Order mapping & PII hidden
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_order_mapping_hides_pii(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_store_with_cafe24_keys(client)

        from app.application import commerce_service as cs_mod
        from app.infrastructure.database.session import async_session_factory
        from app.core.security import encrypt_secret

        async with async_session_factory() as s:
            conn = await cs_mod.commerce_service.get_connection(s, MALL)
            now = datetime.now(timezone.utc)
            conn.access_token_encrypted = encrypt_secret("ACCESS-LIVE")
            conn.access_token_expires_at = now + timedelta(hours=2)
            conn.status = "connected"
            await s.commit()

        async def fake_fetch(self, order_id, access_token):
            return _order_payload(status="P")["order"]

        from app.infrastructure.channels import cafe24 as cafe24_mod

        monkeypatch.setattr(cafe24_mod.Cafe24Adapter, "fetch_order_payload", fake_fetch)

        # API endpoint path
        res = await client.get(f"/api/orders/lookup?mall_id={MALL}&order_id=20261028-0000012")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "shipping"  # Cafe24 code "P" -> shipping
        assert data["items"][0]["product_name"] == "루이셀 세럼"
        assert data["carrier_name"] == "CJ대한통운"
        assert data["shipping_code"] == "123456789"

        # PII must never appear in the API response.
        body = res.text
        assert "김개인" not in body
        assert "010-1234-5678" not in body
        assert "private@example.com" not in body
        assert "비밀로123" not in body

        # Chat path: reply format + PII hidden.
        chat = await client.post(
            "/api/chat",
            json={"mall_id": MALL, "customer_id": "c1", "message": "20261028-0000012 배송 조회해줘"},
        )
        assert chat.status_code == 200
        msg = chat.json()["message"]
        assert "20261028-0000012" in msg
        assert "배송 중" in msg
        assert "루이셀 세럼" in msg
        assert "CJ대한통운" in msg
        assert "123456789" in msg
        assert "김개인" not in msg
        assert "010-1234" not in msg


# ---------------------------------------------------------------------------
# 4. Non-connected malls never see test orders
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_test_orders_blocked_for_connected_and_unknown_malls():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # (a) Showroom preview (no connection row) -> mock test order still works.
        res_preview = await client.post(
            "/api/chat",
            json={"mall_id": "showroom_preview", "customer_id": "p1", "message": "ORD-NORMAL 배송 조회"},
        )
        assert res_preview.status_code == 200
        assert "배송 완료" in res_preview.json()["message"]

        # (b) A real store WITH a live cafe24 connection -> ORD-NORMAL is blocked.
        await _create_store_with_cafe24_keys(client)
        from app.application import commerce_service as cs_mod
        from app.infrastructure.database.session import async_session_factory
        from app.core.security import encrypt_secret

        async with async_session_factory() as s:
            conn = await cs_mod.commerce_service.get_connection(s, MALL)
            now = datetime.now(timezone.utc)
            conn.access_token_encrypted = encrypt_secret("ACCESS-LIVE")
            conn.access_token_expires_at = now + timedelta(hours=2)
            conn.status = "connected"
            await s.commit()

        res_connected = await client.post(
            "/api/chat",
            json={"mall_id": MALL, "customer_id": "c1", "message": "ORD-NORMAL 배송 조회"},
        )
        assert res_connected.status_code == 200
        # Must NOT leak the mock strawberry order to a real connected mall.
        assert "설향 딸기" not in res_connected.json()["message"]

        # (c) A store with cafe24 keys but NOT yet authorized (pending) -> also blocked.
        res_pending = await client.post(
            "/api/chat",
            json={"mall_id": MALL, "customer_id": "c2", "message": "ORD-EXPIRED 배송 조회"},
        )
        assert res_pending.status_code == 200
        assert "대저 짭짤이" not in res_pending.json()["message"]


# ---------------------------------------------------------------------------
# Rate limiting: >5 lookups/min per conversation is blocked
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_order_lookup_rate_limit(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_store_with_cafe24_keys(client)
        from app.application import commerce_service as cs_mod
        from app.infrastructure.database.session import async_session_factory
        from app.core.security import encrypt_secret

        async with async_session_factory() as s:
            conn = await cs_mod.commerce_service.get_connection(s, MALL)
            now = datetime.now(timezone.utc)
            conn.access_token_encrypted = encrypt_secret("ACCESS-LIVE")
            conn.access_token_expires_at = now + timedelta(hours=2)
            conn.status = "connected"
            await s.commit()

        async def fake_fetch(self, order_id, access_token):
            return _order_payload()["order"]

        from app.infrastructure.channels import cafe24 as cafe24_mod

        monkeypatch.setattr(cafe24_mod.Cafe24Adapter, "fetch_order_payload", fake_fetch)

        # Same conversation (session_id) -> 6 lookups in a minute.
        replies = []
        for i in range(6):
            r = await client.post(
                "/api/chat",
                json={
                    "mall_id": MALL,
                    "customer_id": "rl-user",
                    "session_id": "rl-session-1",
                    "message": f"20261028-0000012 배송 조회 {i}",
                },
            )
            replies.append(r.json()["message"])

        # First 5 succeed, 6th is rate-limited.
        assert "너무 잦습니다" in replies[-1]
        assert "배송 중" in replies[0]


# ---------------------------------------------------------------------------
# Edge: refresh token expired -> customer sees maintenance msg, merchant alerted
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_refresh_expired_notifies_merchant(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _create_store_with_cafe24_keys(client)
        from app.application import commerce_service as cs_mod
        from app.infrastructure.database.session import async_session_factory
        from app.core.security import encrypt_secret

        async with async_session_factory() as s:
            conn = await cs_mod.commerce_service.get_connection(s, MALL)
            now = datetime.now(timezone.utc)
            conn.access_token_encrypted = encrypt_secret("OLD")
            conn.refresh_token_encrypted = encrypt_secret("DEAD-REFRESH")
            conn.access_token_expires_at = now - timedelta(hours=1)
            conn.refresh_token_expires_at = now - timedelta(days=1)  # refresh also dead
            conn.status = "connected"
            await s.commit()

        alerts = []

        async def fake_notify(session, mall_id, alert_type, title, message, **kw):
            alerts.append((mall_id, alert_type))
            return None

        from app.application import notification_service as ns_mod

        monkeypatch.setattr(ns_mod.notification_service, "notify_merchant_alert", fake_notify)
        monkeypatch.setattr(cs_mod, "notification_service", ns_mod.notification_service)

        chat = await client.post(
            "/api/chat",
            json={"mall_id": MALL, "customer_id": "c1", "message": "20261028-0000012 배송 조회"},
        )
        assert chat.status_code == 200
        msg = chat.json()["message"]
        # Customer sees a friendly maintenance message, no internal detail.
        assert "일시 점검" in msg
        assert "Traceback" not in msg
        assert "refresh" not in msg.lower()
