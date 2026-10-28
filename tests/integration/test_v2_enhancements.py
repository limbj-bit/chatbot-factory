import io
import pytest
from httpx import ASGITransport, AsyncClient
from app.infrastructure.database.session import init_db
from app.main import app


@pytest.fixture(autouse=True)
async def init_db_fixture():
    await init_db()


@pytest.mark.asyncio
async def test_phase1_and_3_url_crawler_and_ai_counselor_product_cards():
    """
    Verify Enhancement 1 (Store URL/Knowledge Crawler & Multi-tenant RAG)
    and Enhancement 3 (AI Beauty Counselor & Purchase Card Recommendation).
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create a Beauty Store
        store_res = await client.post(
            "/api/stores",
            json={
                "store_name": "루미에르 스킨케어",
                "industry": "beauty",
                "mall_id": "lumiere_skin",
            },
        )
        assert store_res.status_code == 201

        # 2. Crawl a product detail page (using raw_html_override for deterministic offline testing)
        sample_html = """
        <html>
          <head>
            <title>루미에르 퓨어 나이아신아마이드 10% 미백 앰플</title>
            <meta property="product:price:amount" content="38,000" />
            <meta property="og:image" content="https://lumiere.co.kr/img/niacin10.jpg" />
          </head>
          <body>
            <h1>루미에르 퓨어 나이아신아마이드 10% 미백 앰플</h1>
            <p>전성분: 정제수, 나이아신아마이드 10%, 판테놀 2%, 알란토인. 임산부 사용 가능하며 미백과 홍조 진정에 탁월합니다.</p>
          </body>
        </html>
        """
        crawl_res = await client.post(
            "/api/stores/lumiere_skin/knowledge/crawl",
            json={
                "url": "https://lumiere.co.kr/products/niacin-10",
                "raw_html_override": sample_html,
                "tags": "미백,나이아신,홍조,임산부,앰플",
            },
        )
        assert crawl_res.status_code == 201
        learned_doc = crawl_res.json()
        assert "나이아신아마이드 10%" in learned_doc["title"]
        assert learned_doc["price"] == 38000
        assert learned_doc["purchase_url"] == "https://lumiere.co.kr/products/niacin-10"

        # 3. Ask AI Beauty Counselor for a recommendation on this store
        chat_res = await client.post(
            "/api/chat",
            json={
                "mall_id": "lumiere_skin",
                "customer_id": "beauty_shopper_01",
                "message": "임산부인데 나이아신아마이드 미백 앰플 추천해줘",
            },
        )
        assert chat_res.status_code == 200
        chat_data = chat_res.json()
        assert chat_data["intent"] == "ai_counselor_recommendation"
        assert "나이아신아마이드 10%" in chat_data["message"]
        assert len(chat_data["recommended_products"]) >= 1
        top_card = chat_data["recommended_products"][0]
        assert top_card["price"] == 38000
        assert top_card["purchase_url"] == "https://lumiere.co.kr/products/niacin-10"


@pytest.mark.asyncio
async def test_phase2_merchant_webhook_alert_on_manual_review_escalation():
    """
    Verify Enhancement 2: Real-time Merchant Webhook Alert when a claim is escalated to MANUAL_REVIEW.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create Store with webhook_url
        await client.post(
            "/api/stores",
            json={
                "store_name": "글로우 코스메틱",
                "industry": "beauty",
                "mall_id": "glow_webhook_mall",
                "webhook_url": "mock://slack-webhook-glow",
            },
        )

        # 2. Submit duplicate image fraud claim on glow_webhook_mall -> triggers MANUAL_REVIEW -> triggers Merchant Webhook Alert
        identical_image = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"
            + b"WEBHOOK_ESCALATION_TRIGGER"
            + b"\x00" * 200
        )

        c1 = await client.post(
            "/api/claims",
            json={
                "mall_id": "glow_webhook_mall",
                "order_id": "ORD-NORMAL",
                "customer_id": "cust_01",
                "claim_type": "skin_trouble",
                "description": "1차 접수",
            },
        )
        c1_id = c1.json()["claim_id"]
        await client.post(
            f"/api/claims/{c1_id}/images",
            files={"file": ("note1.jpg", io.BytesIO(identical_image), "image/jpeg")},
        )

        claim_res = await client.post(
            "/api/claims",
            json={
                "mall_id": "glow_webhook_mall",
                "order_id": "ORD-NORMAL",
                "customer_id": "vip_customer",
                "claim_type": "skin_trouble",
                "description": "피부 트러블 진단서 확인 요청 (상담원 이관 대상)",
            },
        )
        assert claim_res.status_code == 200
        claim_id = claim_res.json()["claim_id"]

        upload_res = await client.post(
            f"/api/claims/{claim_id}/images",
            files={"file": ("trouble_note.jpg", io.BytesIO(identical_image), "image/jpeg")},
        )
        assert upload_res.status_code == 200
        upload_data = upload_res.json()
        assert upload_data["decision"] == "MANUAL_REVIEW"

        # 4. Verify Webhook Alert Log was created for the merchant
        alerts_res = await client.get("/api/stores/glow_webhook_mall/alerts")
        assert alerts_res.status_code == 200
        alerts = alerts_res.json()
        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "ESCALATE_TO_HUMAN"
        assert alerts[0]["claim_id"] == claim_id
        assert "글로우 코스메틱" in alerts[0]["payload"]["text"]


@pytest.mark.asyncio
async def test_phase4_domain_whitelist_and_daily_ai_quota_enforcement():
    """
    Verify Enhancement 4: Store Domain Whitelist & Daily AI Call Quota Protection.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create Store with strict allowed_domains and daily_quota_limit=2
        await client.post(
            "/api/stores",
            json={
                "store_name": "시크릿 뷰티",
                "industry": "beauty",
                "mall_id": "secret_beauty",
                "allowed_domains": "secretbeauty.co.kr,localhost",
                "daily_quota_limit": 2,
            },
        )

        # 2. Request widget from unauthorized domain -> blocked
        unauth_widget = await client.get(
            "/api/widget/script?mall_id=secret_beauty",
            headers={"Origin": "https://hacker-clone-site.com"},
        )
        assert unauth_widget.status_code == 200
        assert "Unauthorized domain" in unauth_widget.text
        assert "fresh-widget-launcher" not in unauth_widget.text

        # 3. Request widget from authorized domain -> allowed
        auth_widget = await client.get(
            "/api/widget/script?mall_id=secret_beauty",
            headers={"Origin": "https://shop.secretbeauty.co.kr"},
        )
        assert auth_widget.status_code == 200
        assert "fresh-widget-launcher" in auth_widget.text

        # 4. Consume 2 AI chat calls (within daily_quota_limit=2)
        c1 = await client.post(
            "/api/chat",
            json={"mall_id": "secret_beauty", "message": "시카 앰플 성분 알려줘"},
        )
        assert c1.status_code == 200
        assert c1.json()["intent"] != "quota_exceeded"

        c2 = await client.post(
            "/api/chat",
            json={"mall_id": "secret_beauty", "message": "건성 피부 사용법 알려줘"},
        )
        assert c2.status_code == 200
        assert c2.json()["intent"] != "quota_exceeded"

        # 5. 3rd AI chat call exceeds daily_quota_limit=2 -> blocked gracefully
        c3 = await client.post(
            "/api/chat",
            json={"mall_id": "secret_beauty", "message": "세 번째 AI 질문입니다"},
        )
        assert c3.status_code == 200
        assert c3.json()["intent"] == "quota_exceeded"
        assert "한도(2건)가 모두 소진" in c3.json()["message"]

        # 6. Note: 0-token deterministic FAQs still work even when AI quota is exhausted!
        faq_call = await client.post(
            "/api/chat",
            json={"mall_id": "secret_beauty", "message": "배송비 얼마예요?"},
        )
        assert faq_call.status_code == 200
        assert faq_call.json()["intent"] == "faq_deterministic"
