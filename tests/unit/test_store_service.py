import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.application.store_service import store_service
from app.infrastructure.database.models import Base
from app.schemas.store import StoreCreateRequest, StoreSubscriptionUpdateRequest


@pytest.fixture
async def db_session():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_create_electronics_as_store(db_session: AsyncSession):
    req = StoreCreateRequest(
        store_name="한빛 디지털 A/S 센터",
        industry="electronics",
        mall_id="hanbit_digital",
    )
    store_resp = await store_service.create_store(db_session, req)
    assert store_resp.mall_id == "hanbit_digital"
    assert store_resp.industry == "electronics"
    assert store_resp.theme_color == "#1E40AF"
    assert "A/S" in store_resp.welcome_message
    assert '<script src="/api/widget/script?mall_id=hanbit_digital" async></script>' == store_resp.embed_script_tag


@pytest.mark.asyncio
async def test_create_fashion_store_auto_mall_id(db_session: AsyncSession):
    req = StoreCreateRequest(
        store_name="모던 스트릿 패션",
        industry="fashion",
    )
    store_resp = await store_service.create_store(db_session, req)
    assert store_resp.mall_id.startswith("shop_")
    assert store_resp.industry == "fashion"
    assert store_resp.theme_color == "#7C3AED"
    assert "사이즈" in store_resp.welcome_message


@pytest.mark.asyncio
async def test_create_beauty_store(db_session: AsyncSession):
    req = StoreCreateRequest(
        store_name="글로우 뷰티 코스메틱",
        industry="beauty",
        mall_id="glow_beauty_kr",
    )
    store_resp = await store_service.create_store(db_session, req)
    assert store_resp.mall_id == "glow_beauty_kr"
    assert store_resp.industry == "beauty"
    assert store_resp.theme_color == "#EC4899"
    assert "피부" in store_resp.welcome_message
    assert "트러블" in store_resp.welcome_message
    assert store_resp.trial_days == 30
    assert store_resp.is_expired is False
    assert store_resp.expiry_warning is False
    assert store_resp.remaining_days == 30


@pytest.mark.asyncio
async def test_store_trial_expiry_warning_and_extension(db_session: AsyncSession):
    # 1. Create store with 2 days trial -> triggers expiry_warning (<= 3 days)
    req_warn = StoreCreateRequest(
        store_name="임박 뷰티 스토어",
        industry="beauty",
        mall_id="warn_beauty",
        trial_days=2,
    )
    resp_warn = await store_service.create_store(db_session, req_warn)
    assert resp_warn.is_expired is False
    assert resp_warn.expiry_warning is True
    assert resp_warn.remaining_days == 2
    assert "만료 임박" in resp_warn.status_message

    # 2. Create store with 0 days trial -> immediately expired
    req_exp = StoreCreateRequest(
        store_name="만료 뷰티 스토어",
        industry="beauty",
        mall_id="exp_beauty",
        trial_days=0,
    )
    resp_exp = await store_service.create_store(db_session, req_exp)
    assert resp_exp.is_expired is True
    assert resp_exp.remaining_days == 0
    assert "만료되었습니다" in resp_exp.status_message

    # 3. Extend expired store by 30 days -> immediately active and warning cleared
    extended = await store_service.update_subscription(
        db_session,
        "exp_beauty",
        StoreSubscriptionUpdateRequest(extend_days=30, plan_type="active"),
    )
    assert extended is not None
    assert extended.is_expired is False
    assert extended.expiry_warning is False
    assert extended.remaining_days == 30
    assert extended.plan_type == "active"
