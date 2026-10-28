import asyncio
import time
from typing import AsyncIterator, Dict, List, Optional
from app.core.config import settings
from app.core.logging import logger
from app.domain.claims.models import ClaimVisionObservation
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.gemini import GeminiProvider
from app.infrastructure.ai.groq import GroqProvider
from app.infrastructure.ai.mock import MockAIProvider
from app.infrastructure.ai.nvidia import NvidiaProvider


class AIProviderRouter(AIProviderPort):
    """Resilient Multi-Provider Router with 429 Fallback, Circuit Breaker Cooldown, and Retries."""

    def __init__(self, mock_mode: Optional[bool] = None):
        self.mock_mode = mock_mode if mock_mode is not None else settings.MOCK_AI
        self.providers: Dict[str, AIProviderPort] = {}
        self.provider_cooldowns: Dict[str, float] = {}  # provider_name -> cooldown_expiry_timestamp
        self.cooldown_duration_sec: float = 30.0

        self._setup_providers()

    def _setup_providers(self) -> None:
        if self.mock_mode:
            self.mock_provider = MockAIProvider(provider_name="mock")
            self.providers["mock"] = self.mock_provider
            logger.info("AIProviderRouter initialized in MOCK mode.")
            return

        # Real Providers if keys present
        if settings.GROQ_API_KEY:
            self.providers["groq"] = GroqProvider(api_key=settings.GROQ_API_KEY)
        if settings.NVIDIA_API_KEY:
            self.providers["nvidia"] = NvidiaProvider(api_key=settings.NVIDIA_API_KEY)
        if settings.GEMINI_API_KEY:
            self.providers["gemini"] = GeminiProvider(api_key=settings.GEMINI_API_KEY)

        # Fallback to mock if no keys are provided
        if not self.providers:
            logger.warning("No real AI provider keys found in .env. Falling back to MockAIProvider.")
            self.mock_provider = MockAIProvider(provider_name="mock")
            self.providers["mock"] = self.mock_provider

    def is_provider_available(self, name: str) -> bool:
        if name not in self.providers:
            return False
        expiry = self.provider_cooldowns.get(name, 0.0)
        return time.time() > expiry

    def mark_provider_rate_limited(self, name: str) -> None:
        self.provider_cooldowns[name] = time.time() + self.cooldown_duration_sec
        logger.warning(
            f"Provider '{name}' marked as RATE_LIMITED (cooldown {self.cooldown_duration_sec}s)."
        )

    def get_text_provider_chain(self) -> List[str]:
        if self.mock_mode or "mock" in self.providers:
            return ["mock"]
        chain = []
        preferred = [settings.AI_DEFAULT_PROVIDER, settings.AI_FALLBACK_PROVIDER, "gemini"]
        for p in preferred:
            if p in self.providers and p not in chain:
                chain.append(p)
        return chain

    def get_vision_provider_chain(self) -> List[str]:
        if self.mock_mode or "mock" in self.providers:
            return ["mock"]
        chain = []
        if settings.AI_VISION_PROVIDER in self.providers:
            chain.append(settings.AI_VISION_PROVIDER)
        for p in ["gemini", "nvidia", "mock"]:
            if p in self.providers and p not in chain:
                chain.append(p)
        return chain

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        chain = self.get_text_provider_chain()
        last_error = None

        for provider_name in chain:
            if not self.is_provider_available(provider_name):
                logger.info(f"Skipping cooled-down provider: {provider_name}")
                continue

            provider = self.providers[provider_name]
            # Try with bounded exponential backoff
            for attempt in range(2):
                start_time = time.time()
                try:
                    result = await provider.generate_text(prompt, system_prompt)
                    latency_ms = int((time.time() - start_time) * 1000)
                    logger.info(
                        f"AI generation succeeded via provider={provider_name} latency={latency_ms}ms"
                    )
                    return result
                except Exception as exc:
                    err_msg = str(exc)
                    if "429" in err_msg or "rate limit" in err_msg.lower():
                        self.mark_provider_rate_limited(provider_name)
                        last_error = exc
                        break  # Immediately break to next provider on 429
                    logger.warning(
                        f"Provider {provider_name} attempt {attempt + 1} failed: {err_msg}"
                    )
                    last_error = exc
                    await asyncio.sleep(0.2 * (2**attempt))

        logger.error(f"All AI providers failed. Last error: {last_error}")
        return "현재 AI 상담 서비스 접속이 지연되고 있습니다. 잠시 후 다시 시도해 주시거나 고객센터로 문의 바랍니다."

    async def stream_text(self, prompt: str, system_prompt: Optional[str] = None) -> AsyncIterator[str]:
        chain = self.get_text_provider_chain()
        for provider_name in chain:
            if not self.is_provider_available(provider_name):
                continue
            provider = self.providers[provider_name]
            try:
                async for token in provider.stream_text(prompt, system_prompt):
                    yield token
                return
            except Exception as exc:
                logger.warning(f"Provider {provider_name} streaming failed: {exc}. Trying fallback...")
                if "429" in str(exc):
                    self.mark_provider_rate_limited(provider_name)

        yield "현재 일시적인 시스템 지연으로 상담원 연결을 도와드리겠습니다."

    async def analyze_claim_image(self, image_bytes: bytes, mime_type: str) -> ClaimVisionObservation:
        chain = self.get_vision_provider_chain()
        last_error = None

        for provider_name in chain:
            if not self.is_provider_available(provider_name):
                continue
            provider = self.providers[provider_name]
            try:
                observation = await provider.analyze_claim_image(image_bytes, mime_type)
                logger.info(
                    f"Vision analysis completed via {provider_name}: defect={observation.defect_type.value}, damage={observation.damage_ratio_estimate}%"
                )
                return observation
            except Exception as exc:
                if "429" in str(exc):
                    self.mark_provider_rate_limited(provider_name)
                logger.warning(f"Vision provider {provider_name} failed: {exc}")
                last_error = exc

        raise RuntimeError(f"All vision providers failed. Last error: {last_error}")
