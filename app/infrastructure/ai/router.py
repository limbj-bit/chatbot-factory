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
from app.infrastructure.ai.model_pool import parse_model_pool
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
        # Exponential moving average of successful latency (ms) per provider.
        self.provider_latency_ms: Dict[str, float] = {}

        self._setup_providers()

    def _setup_providers(self) -> None:
        if self.mock_mode:
            self.mock_provider = MockAIProvider(provider_name="mock")
            self.providers["mock"] = self.mock_provider
            logger.info("AIProviderRouter initialized in MOCK mode.")
            return

        # Real Providers — each gets a task-tuned default model from settings.
        if settings.GROQ_API_KEY:
            self.providers["groq"] = GroqProvider(
                api_key=settings.GROQ_API_KEY,
                default_model=settings.GROQ_TEXT_MODEL,
            )
        nvidia_key = settings.NVIDIA_API_KEY or settings.NVIDIA_NIM_API_KEY
        nvidia_text_pool = parse_model_pool(
            settings.NVIDIA_TEXT_MODELS, settings.NVIDIA_TEXT_MODEL
        )
        nvidia_vision_pool = parse_model_pool(
            settings.NVIDIA_VISION_MODELS, settings.NVIDIA_VISION_MODEL
        )
        if nvidia_key:
            self.providers["nvidia"] = NvidiaProvider(
                api_key=nvidia_key,
                text_models=nvidia_text_pool,
                vision_models=nvidia_vision_pool,
            )
        if settings.GEMINI_API_KEY:
            self.providers["gemini"] = GeminiProvider(
                api_key=settings.GEMINI_API_KEY,
                default_model=settings.GEMINI_TEXT_MODEL,
            )
        if settings.MISTRAL_API_KEY:
            self.providers["mistral"] = MistralProvider(
                api_key=settings.MISTRAL_API_KEY,
                default_model=settings.MISTRAL_TEXT_MODEL,
            )
        openrouter_text_pool = parse_model_pool(
            settings.OPENROUTER_TEXT_MODELS, settings.OPENROUTER_TEXT_MODEL
        )
        openrouter_vision_pool = parse_model_pool(
            settings.OPENROUTER_VISION_MODELS, settings.OPENROUTER_VISION_MODEL
        )
        if settings.OPENROUTER_API_KEY:
            self.providers["openrouter"] = OpenRouterProvider(
                api_key=settings.OPENROUTER_API_KEY,
                text_models=openrouter_text_pool,
                vision_models=openrouter_vision_pool,
            )
        logger.info(
            "AIProviderRouter live providers=%s models={groq:%s nvidia_text:%s nvidia_vision:%s mistral:%s openrouter_text:%s openrouter_vision:%s gemini:%s}",
            list(self.providers.keys()),
            settings.GROQ_TEXT_MODEL,
            nvidia_text_pool,
            nvidia_vision_pool,
            settings.MISTRAL_TEXT_MODEL,
            openrouter_text_pool,
            openrouter_vision_pool,
            settings.GEMINI_TEXT_MODEL,
        )

        # Fallback to mock if no keys are provided
        if not self.providers:
            logger.warning("No real AI provider keys found in .env. Falling back to MockAIProvider.")
            self.mock_provider = MockAIProvider(provider_name="mock")
            self.providers["mock"] = self.mock_provider

    @property
    def effective_mock_mode(self) -> bool:
        """True when the *router* will actually answer with MockAIProvider.

        `self.mock_mode` alone is the configured intent (settings.MOCK_AI).
        If no provider keys exist, `_setup_providers()` silently installs the
        mock provider without flipping `mock_mode`, so health checks that read
        the config flag can claim "live" while answering with canned text.
        """
        return bool(self.mock_mode or "mock" in self.providers)

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

    def mark_provider_failed(self, name: str, seconds: Optional[float] = None) -> None:
        """Bench a provider after a hard failure (timeout/5xx/bad model)."""
        duration = self.cooldown_duration_sec if seconds is None else seconds
        self.provider_cooldowns[name] = time.time() + duration
        logger.warning(f"Provider '{name}' benched for {duration}s after failure.")

    def _record_latency(self, name: str, latency_ms: float) -> None:
        prev = self.provider_latency_ms.get(name)
        # EMA(0.3) smooths outliers without hiding a consistently slow provider.
        self.provider_latency_ms[name] = (
            latency_ms if prev is None else round(prev * 0.7 + latency_ms * 0.3, 1)
        )

    def get_text_provider_chain(self) -> List[str]:
        """Deterministic speed-first order: fast streaming provider first.

        Previously providers round-robined, so 3 out of 4 messages started on a
        provider whose `stream_text` buffers the whole answer before emitting
        the first token (NVIDIA/OpenRouter/Mistral) — the customer saw a silent
        bubble for 5-12s. Groq (real SSE, high tok/s) must always be tried
        first; the rest are pure failover.
        """
        if self.mock_mode or "mock" in self.providers:
            return ["mock"]

        free_order = ["groq", "nvidia", "openrouter", "mistral"]
        chain: List[str] = []

        for p in (settings.AI_DEFAULT_PROVIDER, settings.AI_FALLBACK_PROVIDER):
            if p in free_order and p in self.providers and p not in chain:
                chain.append(p)
        for p in free_order:
            if p in self.providers and p not in chain:
                chain.append(p)
        for p in self.providers:
            if p not in chain and p not in ("mock", "gemini"):
                chain.append(p)

        if "gemini" in self.providers:
            chain.append("gemini")
        return chain

    def get_status(self) -> Dict[str, object]:
        """Operational snapshot for /health/ai (no secrets)."""
        now = time.time()
        models: Dict[str, object] = {}
        for name, provider in self.providers.items():
            if getattr(provider, "text_models", None):
                models[name] = list(provider.text_models)  # type: ignore[attr-defined]
            elif getattr(provider, "default_model", None):
                models[name] = provider.default_model  # type: ignore[attr-defined]
            else:
                models[name] = "n/a"
        return {
            "mock_mode": self.effective_mock_mode,
            "configured_mock": self.mock_mode,
            "live_provider_count": len([p for p in self.providers if p != "mock"]),
            "provider_order": self.get_text_provider_chain(),
            "vision_order": self.get_vision_provider_chain(),
            "models": models,
            "cooldowns_remaining_sec": {
                name: round(expiry - now, 1)
                for name, expiry in self.provider_cooldowns.items()
                if expiry > now
            },
            "latency_ms_ema": self.provider_latency_ms,
        }

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
                    self._record_latency(provider_name, latency_ms)
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
                    if any(c in err_msg for c in ("404", "410", "403", "not found", "unavailable")):
                        self.mark_provider_failed(provider_name, settings.AI_FAILURE_COOLDOWN_SEC)
                        last_error = exc
                        break  # Break immediately without second retry on dead/forbidden endpoints
                    logger.warning(
                        f"Provider {provider_name} attempt {attempt + 1} failed: {err_msg}"
                    )
                    last_error = exc
                    if attempt == 1:
                        self.mark_provider_failed(
                            provider_name, settings.AI_FAILURE_COOLDOWN_SEC
                        )
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
            agen = provider.stream_text(prompt, system_prompt, history)
            collected: List[str] = []
            started = time.time()
            try:
                # Bound time-to-first-token. Without this, a provider that
                # buffers the whole answer (or hangs) blocks the customer for
                # its full HTTP timeout before failover starts.
                first = await asyncio.wait_for(
                    agen.__anext__(), timeout=settings.AI_STREAM_FIRST_TOKEN_TIMEOUT
                )
            except StopAsyncIteration:
                first = None
                logger.warning(
                    f"Provider {provider_name} streamed 0 tokens; trying fallback..."
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Provider {provider_name} exceeded first-token timeout "
                    f"({settings.AI_STREAM_FIRST_TOKEN_TIMEOUT}s); trying fallback..."
                )
                self.mark_provider_failed(provider_name, settings.AI_FAILURE_COOLDOWN_SEC)
                try:
                    await agen.aclose()
                except Exception:
                    pass
                continue
            except Exception as exc:
                logger.warning(
                    f"Provider {provider_name} streaming failed: {exc}. Trying fallback..."
                )
                if "429" in str(exc) or "rate limit" in str(exc).lower():
                    self.mark_provider_rate_limited(provider_name)
                else:
                    self.mark_provider_failed(provider_name, settings.AI_FAILURE_COOLDOWN_SEC)
                try:
                    await agen.aclose()
                except Exception:
                    pass
                continue

            if first is None:
                try:
                    await agen.aclose()
                except Exception:
                    pass
                continue

            self._record_latency(provider_name, (time.time() - started) * 1000)
            if first:
                collected.append(first)
                yield first
            try:
                async for token in agen:
                    if token:
                        collected.append(token)
                        yield token
            except Exception as exc:
                logger.warning(f"Provider {provider_name} stream broke mid-answer: {exc}")
                # If we already streamed tokens, stop (UI already has text).
                if collected:
                    return
                continue
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
