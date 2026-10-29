"""Guard: claim image filenames must not escape UPLOAD_DIR."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.claim_service import ClaimService
from app.core.config import settings
from app.domain.claims.models import ClaimStatus
from app.domain.policies.models import PolicyDecisionType


@pytest.mark.asyncio
async def test_upload_path_uses_basename_only(tmp_path):
    claim = MagicMock()
    claim.id = "claim-safe-path"
    claim.mall_id = "demo_mall"
    claim.order_id = "ORD-NORMAL"
    claim.customer_id = "cust-1"
    claim.status = ClaimStatus.RECEIVED.value

    def _result():
        r = MagicMock()
        r.scalar_one_or_none.return_value = claim
        r.scalar_one.return_value = 0
        return r

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=lambda *_a, **_k: _result())
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    evil_name = "../../etc/passwd.jpg"

    mock_obs = MagicMock()
    mock_obs.defect_type.value = "bruise"
    mock_obs.damage_ratio_estimate = 5
    mock_obs.confidence = 0.9
    mock_obs.visible_evidence = []
    mock_obs.image_quality.value = "good"

    mock_decision = MagicMock()
    mock_decision.decision = PolicyDecisionType.RETAKE_IMAGE
    mock_decision.reason_code.value = "LOW_DAMAGE"
    mock_decision.refund_ratio = 0
    mock_decision.calculated_amount = 0
    mock_decision.explanation = "ok"

    engine = MagicMock()
    engine.evaluate.return_value = mock_decision

    svc = ClaimService(
        ai_router=MagicMock(analyze_claim_image=AsyncMock(return_value=mock_obs)),
        order_service=MagicMock(get_order_details=AsyncMock(return_value=MagicMock())),
        refund_service=MagicMock(),
    )
    svc._industry_for_mall = AsyncMock(return_value=None)
    svc._policy_engine_for_mall = AsyncMock(return_value=engine)

    with patch.object(settings, "UPLOAD_DIR", str(tmp_path)):
        await svc.process_image_and_evaluate(
            session=session,
            claim_id=claim.id,
            file_bytes=jpeg,
            filename=evil_name,
            declared_mime="image/jpeg",
        )

    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert ".." not in written[0].name
    assert written[0].name.endswith("passwd.jpg")
    assert os.path.commonpath([str(tmp_path), str(written[0])]) == str(tmp_path)
