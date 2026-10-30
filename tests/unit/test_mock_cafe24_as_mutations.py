import pytest
from app.infrastructure.channels.mock_cafe24 import MockCafe24Adapter


@pytest.mark.asyncio
async def test_mock_cancel_exchange_partial_idempotent():
    ad = MockCafe24Adapter()
    assert await ad.cancel_order("ORD-NORMAL", "변심", "k-cancel-1") is True
    assert await ad.cancel_order("ORD-NORMAL", "변심", "k-cancel-1") is True
    assert len(ad._submitted_mutations) == 1

    assert await ad.request_exchange(
        "ORD-NORMAL", ["PROD-1"], "L size", "사이즈", "k-ex-1"
    )
    assert await ad.request_partial_return(
        "ORD-NORMAL",
        ["PROD-STRAWBERRY-01"],
        {"PROD-STRAWBERRY-01": 1},
        "파손",
        "k-pr-1",
    )
    assert ad._submitted_mutations["k-ex-1"]["type"] == "exchange"
    assert ad._submitted_mutations["k-pr-1"]["type"] == "partial_return"
