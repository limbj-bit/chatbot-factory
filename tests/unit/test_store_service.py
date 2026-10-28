import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.application.store_service import store_service
from app.infrastructure.database.models import Base
from app.schemas.store import StoreCreateRequest


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
