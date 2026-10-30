from unittest.mock import patch

import pytest

from app.api.staff_inbox import staff_inbox_token
from app.application.notification_service import NotificationService


def test_staff_inbox_token_stable():
    a = staff_inbox_token("mall_a")
    b = staff_inbox_token("mall_a")
    c = staff_inbox_token("mall_b")
    assert a == b
    assert len(a) == 20
    assert a != c


@pytest.mark.asyncio
async def test_telegram_sendmessage_posts_chat_id_text():
    svc = NotificationService()
    captured = {}

    class FakeResp:
        status_code = 200

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResp()

    with patch("app.application.notification_service.httpx.AsyncClient", FakeClient):
        status = await svc._deliver_http(
            "https://api.telegram.org/botTOKEN/sendMessage?chat_id=12345",
            "hello staff",
            {"text": "hello staff"},
        )
    assert status == "SENT"
    assert captured["url"].endswith("/sendMessage")
    assert "?" not in captured["url"]
    assert captured["json"] == {"chat_id": "12345", "text": "hello staff"}


@pytest.mark.asyncio
async def test_email_skipped_without_smtp():
    svc = NotificationService()
    status = await svc._deliver_email("a@b.com", "Shop", "T", "body")
    assert status == "EMAIL_SKIPPED_NO_SMTP"
