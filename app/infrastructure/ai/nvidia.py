import base64
import json
import httpx
from typing import AsyncIterator, Dict, List, Optional
from app.domain.claims.models import ClaimVisionObservation, DefectType, ImageQuality
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.messages import build_openai_messages
from app.infrastructure.ai.vision_prompts import build_vision_instruction


def _parse_vision_json(raw: str) -> ClaimVisionObservation:
    """Parse the vision model's JSON output into a ClaimVisionObservation.

    Tolerant of code-fences and unknown enum values (maps to UNCLEAR/ACCEPTABLE).
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    try:
        parsed = json.loads(text)
    except Exception:
        # Try to salvage the first {...} block
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(text[start : end + 1])
        else:
            raise

    def _defect(v: str) -> DefectType:
        try:
            return DefectType(str(v).strip().lower())
        except Exception:
            return DefectType.UNCLEAR

    def _quality(v: str) -> ImageQuality:
        try:
            return ImageQuality(str(v).strip().lower())
        except Exception:
            return ImageQuality.ACCEPTABLE

    return ClaimVisionObservation(
        defect_type=_defect(parsed.get("defect_type", "unclear")),
        affected_items=int(parsed.get("affected_items", 1) or 1),
        damage_ratio_estimate=max(0, min(100, int(parsed.get("damage_ratio_estimate", 0) or 0))),
        confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.5) or 0.5))),
        visible_evidence=parsed.get("visible_evidence", []) or [],
        image_quality=_quality(parsed.get("image_quality", "acceptable")),
    )


class NvidiaProvider(AIProviderPort):
    """NVIDIA NIM API Adapter for complex reasoning, classification, and fallback."""

    BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        default_model: str = "meta/llama-3.1-70b-instruct",
        vision_model: str = "microsoft/phi-3.5-vision-instruct",
    ):
        self.api_key = api_key
        self.default_model = default_model
        self.vision_model = vision_model

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        messages = build_openai_messages(prompt, system_prompt, history)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.default_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.BASE_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: NVIDIA NIM rate limit")
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        # Simple streaming fallback or direct full-text yield
        full_text = await self.generate_text(prompt, system_prompt, history)
        words = full_text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    async def analyze_claim_image(
        self, image_bytes: bytes, mime_type: str, industry: Optional[str] = None
    ) -> ClaimVisionObservation:
        """Real multimodal vision via NVIDIA NIM (phi-3.5-vision)."""
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64_img}"
        instruction = build_vision_instruction(industry)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 512,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.BASE_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: NVIDIA NIM rate limit")
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            return _parse_vision_json(raw)
