import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.domain.claims.models import ClaimStatus
from app.domain.policies.models import PolicyDecisionResult, PolicyDecisionType, PolicyReasonCode
from app.infrastructure.channels.mock_cafe24 import MockCafe24Adapter
from app.infrastructure.database.models import Base, ClaimModel, RefundDecisionModel
from app.application.refund_service import RefundService


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
async def test_refund_service_idempotency(db_session: AsyncSession):
    channel = MockCafe24Adapter()
    refund_service = RefundService(channel_adapter=channel)

    claim_id = str(uuid.uuid4())
    claim = ClaimModel(
        id=claim_id,
        order_id="ORD-NORMAL",
        customer_id="CUST-001",
        claim_type="fresh_defect",
        status=ClaimStatus.POLICY_EVALUATING.value,
        description="딸기 곰팡이",
    )
    db_session.add(claim)
    await db_session.commit()

    decision = PolicyDecisionResult(
        decision=PolicyDecisionType.FULL_REFUND,
        reason_code=PolicyReasonCode.SEVERE_DAMAGE,
        requires_manual_review=False,
        refund_ratio=100,
        explanation="Severe damage",
        suggested_customer_message="전액 환불",
        calculated_amount=24000,
    )

    # 1. First execution
    op_id = "op-fixed-12345"
    success1 = await refund_service.execute_refund(
        session=db_session,
        claim=claim,
        decision_result=decision,
        operation_id=op_id,
    )
    assert success1 is True
    assert claim.status == ClaimStatus.AUTO_APPROVED.value
    assert claim.refund_amount == 24000

    # 2. Second execution with identical op_id
    success2 = await refund_service.execute_refund(
        session=db_session,
        claim=claim,
        decision_result=decision,
        operation_id=op_id,
    )
    assert success2 is True

    # Check database: exactly 1 refund_decisions record should exist
    from sqlalchemy import select
    records = await db_session.execute(select(RefundDecisionModel).where(RefundDecisionModel.claim_id == claim_id))
    all_records = records.scalars().all()
    assert len(all_records) == 1
    assert all_records[0].execution_status == "SUCCESS"


@pytest.mark.asyncio
async def test_refund_service_unknown_external_state(db_session: AsyncSession):
    # Mock channel that throws Timeout
    class TimeoutChannel(MockCafe24Adapter):
        async def register_return_request(self, *args, **kwargs) -> bool:
            raise TimeoutError("External gateway timeout")

    refund_service = RefundService(channel_adapter=TimeoutChannel())

    claim_id = str(uuid.uuid4())
    claim = ClaimModel(
        id=claim_id,
        order_id="ORD-NORMAL",
        customer_id="CUST-001",
        claim_type="fresh_defect",
        status=ClaimStatus.POLICY_EVALUATING.value,
        description="딸기 곰팡이",
    )
    db_session.add(claim)
    await db_session.commit()

    decision = PolicyDecisionResult(
        decision=PolicyDecisionType.FULL_REFUND,
        reason_code=PolicyReasonCode.SEVERE_DAMAGE,
        requires_manual_review=False,
        refund_ratio=100,
        explanation="Severe damage",
        suggested_customer_message="전액 환불",
        calculated_amount=24000,
    )

    success = await refund_service.execute_refund(
        session=db_session,
        claim=claim,
        decision_result=decision,
        operation_id="timeout_op_1",
    )
    assert success is False
    assert claim.status == ClaimStatus.UNKNOWN_EXTERNAL_STATE.value
