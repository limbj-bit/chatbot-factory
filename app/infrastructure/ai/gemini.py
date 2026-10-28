import base64
import json
import httpx
from typing import AsyncIterator, Dict, List, Optional
from app.domain.claims.models import ClaimVisionObservation, DefectType, ImageQuality
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.nvidia import _parse_vision_json
from app.infrastructure.ai.vision_prompts import build_vision_instruction


class GeminiProvider(AIProviderPort):
    """Google Gemini API Adapter for Multimodal Vision Observation and Text Generation."""

    def __init__(self, api_key: str, default_model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.default_model = default_model

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.default_model}:generateContent?key={self.api_key}"

        # Gemini uses alternating user/model turns (no separate "system" role),
        # so the system prompt is folded into the FIRST user turn to frame the
        # whole conversation (mirrors the OpenAI-style "system" message ordering).
        prefix = f"System Instructions:\n{system_prompt}\n\n" if system_prompt else ""
        contents: List[Dict] = []
        if history:
            for turn in history:
                if not isinstance(turn, dict):
                    continue
                role = turn.get("role")
                text = (turn.get("content") or "").strip()
                if role not in ("user", "assistant") or not text:
                    continue
                mapped_role = "user" if role == "user" else "model"
                # Fold the system prompt into the first turn; if the first turn
                # is a model reply, emit a dedicated leading user turn instead.
                if prefix and not contents:
                    if mapped_role == "user":
                        text = prefix + text
                        prefix = ""
                    else:
                        contents.append({"role": "user", "parts": [{"text": prefix}]})
                        prefix = ""
                contents.append({"role": mapped_role, "parts": [{"text": text}]})
        # Any leftover prefix (no usable history) rides with the final prompt.
        contents.append({"parts": [{"text": prefix + prompt}]})

        payload = {"contents": contents}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: Gemini rate limit")
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

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

    async def analyze_claim_image(
        self, image_bytes: bytes, mime_type: str, industry: Optional[str] = None
    ) -> ClaimVisionObservation:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.default_model}:generateContent?key={self.api_key}"

        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        vision_instruction = build_vision_instruction(industry)

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
            return _parse_vision_json(raw_json)
