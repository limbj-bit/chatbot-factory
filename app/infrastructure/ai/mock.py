import asyncio
import json
from typing import AsyncIterator, Dict, List, Optional
from app.domain.claims.models import ClaimVisionObservation, DefectType, ImageQuality
from app.domain.ports.ai_port import AIProviderPort


class MockAIProvider(AIProviderPort):
    """Deterministic Mock AI Provider for testing and keyless local development."""

    def __init__(self, provider_name: str = "mock"):
        self.provider_name = provider_name
        self.simulate_429: bool = False
        self.simulate_timeout: bool = False
        self.simulate_error: bool = False

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        if self.simulate_429:
            raise RuntimeError("429 Too Many Requests: Rate limit exceeded")
        if self.simulate_timeout:
            raise TimeoutError("Provider request timed out after 5000ms")
        if self.simulate_error:
            raise RuntimeError("500 Internal Server Error: Provider failure")

        if "배송" in prompt:
            return "고객님의 주문은 현재 배송 준비 중이며, 보통 영업일 기준 1~2일 내 배송이 완료됩니다."
        elif "딸기" in prompt:
            return "설향 딸기는 수령 즉시 냉장 보관(0~4도)하시고 가급적 2일 이내에 섭취하시는 것이 좋습니다."
        # Multi-turn aware: acknowledge prior turns so tests can assert memory works.
        if history:
            last_user = next(
                (h["content"] for h in reversed(history) if h.get("role") == "user"),
                "",
            )
            if last_user:
                return f"네, 아까 말씀드린 '{last_user[:20]}' 기준으로 안내드립니다. 무엇을 더 도와드릴까요?"
        return "안녕하세요! 신선식품 고객센터 AI 도우미입니다. 무엇을 도와드릴까요?"

    async def stream_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        full_text = await self.generate_text(prompt, system_prompt, history)
        words = full_text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.01)

    async def analyze_claim_image(
        self, image_bytes: bytes, mime_type: str, industry: str = None
    ) -> ClaimVisionObservation:
        if self.simulate_429:
            raise RuntimeError("429 Too Many Requests: Rate limit exceeded")
        if self.simulate_timeout:
            raise TimeoutError("Provider request timed out")
        if self.simulate_error:
            raise RuntimeError("500 Internal Server Error")

        # Determine response based on simulated test payloads or content length
        if len(image_bytes) < 32 or b"BLURRY_TRIGGER" in image_bytes:
            return ClaimVisionObservation(
                defect_type=DefectType.UNCLEAR,
                affected_items=0,
                damage_ratio_estimate=0,
                confidence=0.40,
                visible_evidence=["초점 불량 및 피사체 흐림"],
                image_quality=ImageQuality.BLURRY,
            )

        if b"NORMAL_TRIGGER" in image_bytes:
            return ClaimVisionObservation(
                defect_type=DefectType.NORMAL,
                affected_items=0,
                damage_ratio_estimate=0,
                confidence=0.95,
                visible_evidence=["신선 과일 특성 정상"],
                image_quality=ImageQuality.ACCEPTABLE,
            )

        if b"PARTIAL_TRIGGER" in image_bytes:
            return ClaimVisionObservation(
                defect_type=DefectType.BRUISE,
                affected_items=1,
                damage_ratio_estimate=15,
                confidence=0.89,
                visible_evidence=["표면 충격 압착 및 과육 일부 물러짐"],
                image_quality=ImageQuality.ACCEPTABLE,
            )

        # Default standard damage observation
        return ClaimVisionObservation(
            defect_type=DefectType.MOLD,
            affected_items=3,
            damage_ratio_estimate=35,
            confidence=0.92,
            visible_evidence=["흰색 곰팡이 포자 군집", "과육 짓물림 및 변색"],
            image_quality=ImageQuality.ACCEPTABLE,
        )
