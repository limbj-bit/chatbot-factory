import pytest
from app.infrastructure.ai.mock import MockAIProvider
from app.infrastructure.ai.router import AIProviderRouter


@pytest.mark.asyncio
async def test_router_normal_text_generation():
    router = AIProviderRouter(mock_mode=True)
    response = await router.generate_text("배송 언제 오나요?")
    assert "배송" in response


@pytest.mark.asyncio
async def test_router_stream_text():
    router = AIProviderRouter(mock_mode=True)
    tokens = []
    async for token in router.stream_text("딸기 보관법"):
        tokens.append(token)
    full_response = "".join(tokens)
    assert len(tokens) > 1
    assert "딸기" in full_response


@pytest.mark.asyncio
async def test_router_429_fallback_and_cooldown():
    router = AIProviderRouter(mock_mode=False)

    # Inject two mock providers to test fallback
    provider_primary = MockAIProvider(provider_name="groq_mock")
    provider_fallback = MockAIProvider(provider_name="nvidia_mock")

    # Simulate 429 on primary
    provider_primary.simulate_429 = True

    router.providers = {
        "groq": provider_primary,
        "nvidia": provider_fallback,
    }

    # Should catch 429, mark groq in cooldown, and succeed via nvidia
    response = await router.generate_text("배송 상태 알려줘")
    assert "배송" in response
    assert not router.is_provider_available("groq")
    assert router.is_provider_available("nvidia")


@pytest.mark.asyncio
async def test_router_all_providers_failing_returns_graceful_message():
    router = AIProviderRouter(mock_mode=False)
    p1 = MockAIProvider(provider_name="p1")
    p1.simulate_error = True
    p2 = MockAIProvider(provider_name="p2")
    p2.simulate_error = True

    router.providers = {"groq": p1, "nvidia": p2}

    response = await router.generate_text("테스트 질문")
    assert "고객센터로 문의" in response


@pytest.mark.asyncio
async def test_router_vision_analysis():
    router = AIProviderRouter(mock_mode=True)
    dummy_img = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    observation = await router.analyze_claim_image(dummy_img, "image/jpeg")
    assert observation.damage_ratio_estimate == 35
    assert observation.confidence > 0.8
    assert observation.is_acceptable_quality()
