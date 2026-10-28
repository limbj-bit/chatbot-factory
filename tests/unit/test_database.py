import pytest
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.infrastructure.database.models import Base, ClaimModel, SessionModel, MessageModel


@pytest.fixture
async def test_session():
    # In-memory SQLite for testing
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_session_and_message_persistence(test_session: AsyncSession):
    session_id = str(uuid.uuid4())
    chat_session = SessionModel(
        id=session_id,
        customer_id="CUST-001",
        channel="web_widget",
    )
    test_session.add(chat_session)
    await test_session.commit()

    message = MessageModel(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="user",
        content="배송 언제 오나요?",
        intent="shipping_inquiry",
    )
    test_session.add(message)
    await test_session.commit()

    # Query back
    result = await test_session.execute(select(SessionModel).where(SessionModel.id == session_id))
    fetched_session = result.scalar_one_or_none()
    assert fetched_session is not None
    assert fetched_session.customer_id == "CUST-001"


@pytest.mark.asyncio
async def test_claim_persistence(test_session: AsyncSession):
    claim_id = str(uuid.uuid4())
    claim = ClaimModel(
        id=claim_id,
        order_id="ORD-2026-001",
        customer_id="CUST-001",
        claim_type="fresh_defect",
        status="RECEIVED",
        description="딸기가 물러서 왔습니다.",
        idempotency_key=f"claim:{claim_id}:init",
    )
    test_session.add(claim)
    await test_session.commit()

    result = await test_session.execute(select(ClaimModel).where(ClaimModel.id == claim_id))
    fetched_claim = result.scalar_one_or_none()
    assert fetched_claim is not None
    assert fetched_claim.order_id == "ORD-2026-001"
    assert fetched_claim.status == "RECEIVED"
