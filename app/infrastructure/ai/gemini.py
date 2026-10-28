import base64
import json
import httpx
from typing import AsyncIterator, Optional
from app.domain.claims.models import ClaimVisionObservation, DefectType, ImageQuality
from app.domain.ports.ai_port import AIProviderPort


class GeminiProvider(AIProviderPort):
    """Google Gemini API Adapter for Multimodal Vision Observation and Text Generation."""

    def __init__(self, api_key: str, default_model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.default_model = default_model

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.default_model}:generateContent?key={self.api_key}"
        parts = []
        if system_prompt:
            parts.append({"text": f"System Instructions:\n{system_prompt}\n\n"})
        parts.append({"text": prompt})

        payload = {"contents": [{"parts": parts}]}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: Gemini rate limit")
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def stream_text(self, prompt: str, system_prompt: Optional[str] = None) -> AsyncIterator[str]:
        full_text = await self.generate_text(prompt, system_prompt)
        words = full_text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    async def analyze_claim_image(self, image_bytes: bytes, mime_type: str) -> ClaimVisionObservation:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.default_model}:generateContent?key={self.api_key}"

        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        vision_instruction = (
            "Analyze this fresh food product image for physical damage or defects.\n"
            "Respond ONLY with a valid JSON object matching this schema:\n"
            "{\n"
            '  "defect_type": "mold" | "rot" | "bruise" | "crush_damage" | "cosmetic_defect" | "normal" | "unclear",\n'
            '  "affected_items": <integer>,\n'
            '  "damage_ratio_estimate": <integer 0-100>,\n'
            '  "confidence": <float 0.0-1.0>,\n'
            '  "visible_evidence": [<string>, ...],\n'
            '  "image_quality": "acceptable" | "blurry" | "too_dark" | "occluded" | "invalid"\n'
            "}\n"
            "Do NOT make refund or business decisions. Only report physical observations."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": vision_instruction},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_img,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: Gemini rate limit")
            resp.raise_for_status()
            data = resp.json()
            raw_json = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_json)

            return ClaimVisionObservation(
                defect_type=DefectType(parsed.get("defect_type", "unclear")),
                affected_items=int(parsed.get("affected_items", 1)),
                damage_ratio_estimate=int(parsed.get("damage_ratio_estimate", 0)),
                confidence=float(parsed.get("confidence", 0.5)),
                visible_evidence=parsed.get("visible_evidence", []),
                image_quality=ImageQuality(parsed.get("image_quality", "acceptable")),
            )
