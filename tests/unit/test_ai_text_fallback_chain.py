"""Text/vision chains: rotate free APIs; Gemini always last paid resort."""
from app.core.config import settings
from app.infrastructure.ai.router import AIProviderRouter


def _live_router(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_AI", False)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "g")
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "n")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "o")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "m")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "paid")
    monkeypatch.setattr(settings, "AI_DEFAULT_PROVIDER", "groq")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "nvidia")
    return AIProviderRouter(mock_mode=False)


def test_text_chain_includes_all_free_and_gemini_last(monkeypatch):
    router = _live_router(monkeypatch)
    chain = router.get_text_provider_chain()
    assert set(chain[:-1]) == {"groq", "nvidia", "openrouter", "mistral"}
    assert chain[-1] == "gemini"


def test_text_chain_rotates_free_start(monkeypatch):
    router = _live_router(monkeypatch)
    starts = [router.get_text_provider_chain()[0] for _ in range(8)]
    # Round-robin should use more than one free provider as the first hop
    assert len(set(starts)) >= 2
    for _ in range(4):
        assert router.get_text_provider_chain()[-1] == "gemini"


def test_gemini_stays_last_even_if_set_as_default(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_AI", False)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "g")
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "n")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "o")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "m")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "paid")
    monkeypatch.setattr(settings, "AI_DEFAULT_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "groq")

    router = AIProviderRouter(mock_mode=False)
    chain = router.get_text_provider_chain()
    assert chain[-1] == "gemini"
    assert chain[0] != "gemini"


def test_intake_reply_for_vague_beauty_recommend():
    from app.application.chat_service import ChatService

    msg = "✨ 피부타입별맞춤 상품 추천"
    out = ChatService._deterministic_intake_reply("beauty", msg, msg)
    assert out is not None
    assert "피부타입" in out
    assert ChatService._deterministic_intake_reply("beauty", "건성인데 보습 추천", "건성인데 보습 추천") is None


def test_vision_chain_nvidia_openrouter_then_gemini(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_AI", False)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "g")
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "n")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "o")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "paid")
    monkeypatch.setattr(settings, "AI_VISION_PROVIDER", "gemini")  # must NOT jump ahead

    router = AIProviderRouter(mock_mode=False)
    chain = router.get_vision_provider_chain()
    assert chain == ["nvidia", "openrouter", "gemini"]
