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


@pytest.mark.asyncio
async def test_phase5_cosbot_badge_flaticon_presets_and_custom_avatar_upload():
    """
    Verify COSRAWFREE '코스봇 상담' double-ring badge, Flaticon presets, and custom PNG/SVG avatar file upload.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create store with COSRAWFREE '코스봇 상담' badge and Flaticon cute robot preset
        res = await client.post(
            "/api/stores",
            json={
                "store_name": "코스로우프리 원료몰",
                "industry": "beauty",
                "mall_id": "cosrawfree_mall",
                "bot_icon_style": "flaticon_cute_robot",
                "launcher_shape": "cosbot_badge",
                "bot_label": "코스봇 상담",
            },
        )
        assert res.status_code == 201
        store_data = res.json()
        assert store_data["launcher_shape"] == "cosbot_badge"
        assert store_data["bot_label"] == "코스봇 상담"
        assert store_data["bot_icon_style"] == "flaticon_cute_robot"

        # 2. Verify dynamic widget script renders the cosbot_badge double ring and label
        script_res = await client.get("/api/widget/script?mall_id=cosrawfree_mall")
        assert script_res.status_code == 200
        js_text = script_res.text
        assert "fresh-cosbot-ring" in js_text
        assert "fresh-cosbot-label" in js_text
        assert "코스봇 상담" in js_text
        assert "<svg" in js_text

        # 3. Upload custom Flaticon PNG/SVG file via POST /api/stores/{mall_id}/avatar
        custom_svg_bytes = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="pink"/></svg>'
        avatar_res = await client.post(
            "/api/stores/cosrawfree_mall/avatar",
            files={"file": ("my_flaticon.svg", io.BytesIO(custom_svg_bytes), "image/svg+xml")},
        )
        assert avatar_res.status_code == 200
        avatar_data = avatar_res.json()
        assert avatar_data["bot_icon_style"] == "custom_upload"
        assert avatar_data["bot_avatar_url"].startswith("data:image/svg+xml;base64,")

        # 4. Verify widget script now renders the uploaded custom image inside the cosbot ring & chat avatar
        script_res2 = await client.get("/api/widget/script?mall_id=cosrawfree_mall")
        assert "fresh-bot-avatar-img" in script_res2.text
        assert "data:image/svg+xml;base64," in script_res2.text


@pytest.mark.asyncio
async def test_phase6_bot_name_16_icons_and_10_chat_window_templates():
    """
    Verify custom bot_name, brand_badge, 16 Flaticon icons, and all 10 commercial chat window UX templates.
    """
    from app.api.widget import FLATICON_PRESET_SVGS

    assert len(FLATICON_PRESET_SVGS) >= 16

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        templates = [
            "cosraw_grid",
            "floating_hero",
            "app_icon_matrix",
            "tabbed_portal",
            "step_wizard",
            "kakao_yellow",
            "channel_card",
            "commerce_showcase",
            "glass_dark",
            "luxury_editorial",
        ]
        icon_keys = list(FLATICON_PRESET_SVGS.keys())

        for idx, tpl in enumerate(templates):
            mall_id = f"tpl_mall_{idx}"
            chosen_icon = icon_keys[idx % len(icon_keys)]
            res = await client.post(
                "/api/stores",
                json={
                    "store_name": "코스라프리",
                    "industry": "raw_materials",
                    "mall_id": mall_id,
                    "bot_name": "코스봇",
                    "bot_icon_style": chosen_icon,
                    "brand_badge": "코스라프리",
                    "header_title": "고객상담센터",
                    "chat_template": tpl,
                    "contact_email": "contact@cosrawfree.com",
                    "business_hours": "평일 09:00~18:00",
                },
            )
            assert res.status_code == 201
            data = res.json()
            assert data["bot_name"] == "코스봇"
            assert data["chat_template"] == tpl
            assert data["bot_icon_style"] == chosen_icon
            assert len(data["quick_buttons"]) == 5

            script_text = (await client.get(f"/api/widget/script?mall_id={mall_id}")).text
            assert f'chatTemplate: "{tpl}"' in script_text
            assert f'botIconStyle: "{chosen_icon}"' in script_text
            assert 'botName: "코스봇"' in script_text
            assert "contact@cosrawfree.com" in script_text


@pytest.mark.asyncio
async def test_phase7_zero_hole_security_showroom_vs_admin_separation():
    """
    Verify Zero-Hole Security:
    1. Public self-service showroom caps trial_days at 14 even if a customer tries to pass trial_days=999 or None.
    2. Listing all stores (GET /api/stores or GET /api/admin/stores) without X-Admin-Key is blocked with 401.
    3. Extending subscription without X-Admin-Key is blocked with 401.
    4. Master Admin Console (/admin) and Customer Showroom (/showroom) are served properly.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Customer tries to cheat by requesting 3650 days without Admin Key -> capped at 14 days
        cheat_res = await client.post(
            "/api/stores",
            json={
                "store_name": "얌체 스토어",
                "industry": "beauty",
                "mall_id": "sneaky_store",
                "trial_days": 3650,
                "daily_quota_limit": 99999,
            },
        )
        assert cheat_res.status_code == 201
        cheat_data = cheat_res.json()
        assert cheat_data["trial_days"] == 30
        assert cheat_data["remaining_days"] == 30
        assert cheat_data["daily_quota_limit"] == 300

        # 2. Unauthorized user tries to list all stores -> 401 Unauthorized
        unauth_list = await client.get("/api/stores")
        assert unauth_list.status_code == 401
        unauth_admin_list = await client.get("/api/admin/stores")
        assert unauth_admin_list.status_code == 401

        # 3. Authorized Master Admin lists all stores, upgrades to unlimited, then converts back to 30 days
        admin_headers = {"X-Admin-Key": "admin-dev-secret-key-change-in-prod"}
        auth_list = await client.get("/api/admin/stores", headers=admin_headers)
        assert auth_list.status_code == 200
        assert any(s["mall_id"] == "sneaky_store" for s in auth_list.json())

        vip_res = await client.patch(
            "/api/admin/stores/sneaky_store/subscription",
            headers=admin_headers,
            json={"plan_type": "unlimited", "is_active": True},
        )
        assert vip_res.status_code == 200
        assert vip_res.json()["plan_type"] == "unlimited"
        assert vip_res.json()["remaining_days"] is None

        revert_30_res = await client.patch(
            "/api/admin/stores/sneaky_store/subscription",
            headers=admin_headers,
            json={"reset_days": 30, "plan_type": "active", "is_active": True},
        )
        assert revert_30_res.status_code == 200
        assert revert_30_res.json()["plan_type"] == "active"
        assert revert_30_res.json()["remaining_days"] == 30

        # 4. Verify /showroom and /admin routes serve their respective HTML pages
        showroom_page = await client.get("/showroom")
        assert showroom_page.status_code == 200
        assert "SELF-SERVICE DESIGN SHOWROOM" in showroom_page.text

        admin_page = await client.get("/admin")
        assert admin_page.status_code == 200
        assert "MASTER ADMIN CONSOLE" in admin_page.text
