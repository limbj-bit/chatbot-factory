import asyncio
import time
from typing import AsyncIterator, Dict, List, Optional
from app.core.config import settings
from app.core.logging import logger
from app.domain.claims.models import ClaimVisionObservation
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.gemini import GeminiProvider
from app.infrastructure.ai.groq import GroqProvider
from app.infrastructure.ai.mistral import MistralProvider
from app.infrastructure.ai.mock import MockAIProvider
from app.infrastructure.ai.nvidia import NvidiaProvider
from app.infrastructure.ai.openrouter import OpenRouterProvider


class AIProviderRouter(AIProviderPort):
    """Resilient Multi-Provider Router with 429 Fallback, Circuit Breaker Cooldown, and Retries."""

    def __init__(self, mock_mode: Optional[bool] = None):
        has_real_key = bool(
            settings.GROQ_API_KEY
            or settings.NVIDIA_API_KEY
            or settings.NVIDIA_NIM_API_KEY
            or settings.GEMINI_API_KEY
            or settings.MISTRAL_API_KEY
            or settings.OPENROUTER_API_KEY
        )
        if mock_mode is not None:
            self.mock_mode = mock_mode
        elif settings.APP_ENV == "production" and has_real_key:
            self.mock_mode = False
        else:
            self.mock_mode = settings.MOCK_AI
        self.providers: Dict[str, AIProviderPort] = {}
        self.provider_cooldowns: Dict[str, float] = {}  # provider_name -> cooldown_expiry_timestamp
        self.cooldown_duration_sec: float = 30.0
        # Rotate which free provider is tried first across requests (Gemini stays last).
        self._free_rr_index: int = 0

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
        nvidia_key = settings.NVIDIA_API_KEY or settings.NVIDIA_NIM_API_KEY
        if nvidia_key:
            self.providers["nvidia"] = NvidiaProvider(api_key=nvidia_key)
        if settings.GEMINI_API_KEY:
            self.providers["gemini"] = GeminiProvider(api_key=settings.GEMINI_API_KEY)
        if settings.MISTRAL_API_KEY:
            self.providers["mistral"] = MistralProvider(api_key=settings.MISTRAL_API_KEY)
        if settings.OPENROUTER_API_KEY:
            self.providers["openrouter"] = OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY)
        logger.info(f"AIProviderRouter initialized with live providers: {list(self.providers.keys())}")

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
        """Free providers first; Gemini is always the paid last resort.

        Order: groq → nvidia → openrouter → mistral → (other free) → gemini.
        AI_DEFAULT / AI_FALLBACK only reorder among free providers — never
        pull Gemini ahead of free APIs.
        """
        if self.mock_mode or "mock" in self.providers:
            return ["mock"]

        free_order = ["groq", "nvidia", "openrouter", "mistral"]
        free: List[str] = []

        for p in (settings.AI_DEFAULT_PROVIDER, settings.AI_FALLBACK_PROVIDER):
            if p in free_order and p in self.providers and p not in free:
                free.append(p)
        for p in free_order:
            if p in self.providers and p not in free:
                free.append(p)
        for p in self.providers:
            if p not in free and p not in ("mock", "gemini"):
                free.append(p)

        # Round-robin start among free providers so Groq/NVIDIA/OpenRouter/Mistral
        # all share load; on failure we still walk the full free list then Gemini.
        if free:
            start = self._free_rr_index % len(free)
            self._free_rr_index += 1
            free = free[start:] + free[:start]

        if "gemini" in self.providers:
            return free + ["gemini"]
        return free

    def get_vision_provider_chain(self) -> List[str]:
        """Vision: free NVIDIA → OpenRouter, then paid Gemini last.

        AI_VISION_PROVIDER may reorder among free vision providers only —
        Gemini is never pulled ahead of NVIDIA/OpenRouter.
        """
        if self.mock_mode or "mock" in self.providers:
            return ["mock"]
        free_vision = ["nvidia", "openrouter"]
        chain: List[str] = []
        preferred = settings.AI_VISION_PROVIDER
        if preferred in free_vision and preferred in self.providers:
            chain.append(preferred)
        for p in free_vision:
            if p in self.providers and p not in chain:
                chain.append(p)
        if "gemini" in self.providers:
            chain.append("gemini")
        return chain

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List] = None,
    ) -> str:
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
                    result = await provider.generate_text(prompt, system_prompt, history)
                    text = (result or "").strip()
                    # Too-short / empty answers are treated as soft failures so the
                    # next free provider (and finally Gemini) can try for better quality.
                    if len(text) < 12:
                        logger.warning(
                            f"Provider {provider_name} returned weak/empty text "
                            f"(len={len(text)}); trying fallback..."
                        )
                        last_error = RuntimeError(f"{provider_name} weak response")
                        break
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

    async def stream_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List] = None,
    ) -> AsyncIterator[str]:
        chain = self.get_text_provider_chain()
        for provider_name in chain:
            if not self.is_provider_available(provider_name):
                continue
            provider = self.providers[provider_name]
            collected: List[str] = []
            try:
                async for token in provider.stream_text(prompt, system_prompt, history):
                    if token:
                        collected.append(token)
                        yield token
                # Empty successful stream → try next provider (do not treat as done)
                if collected:
                    return
                logger.warning(
                    f"Provider {provider_name} streamed 0 tokens; trying fallback..."
                )
            except Exception as exc:
                logger.warning(f"Provider {provider_name} streaming failed: {exc}. Trying fallback...")
                if "429" in str(exc) or "rate limit" in str(exc).lower():
                    self.mark_provider_rate_limited(provider_name)
                # If we already streamed partial tokens, stop (UI already has text)
                if collected:
                    return

        yield "현재 일시적인 시스템 지연으로 상담원 연결을 도와드리겠습니다."

    async def analyze_claim_image(
        self, image_bytes: bytes, mime_type: str, industry: Optional[str] = None
    ) -> ClaimVisionObservation:
        chain = self.get_vision_provider_chain()
        last_error = None

        for provider_name in chain:
            if not self.is_provider_available(provider_name):
                continue
            provider = self.providers[provider_name]
            try:
                observation = await provider.analyze_claim_image(image_bytes, mime_type, industry)
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
