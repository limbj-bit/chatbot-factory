import base64
import json
import httpx
from typing import AsyncIterator, Dict, List, Optional, Union
from app.domain.claims.models import ClaimVisionObservation, DefectType, ImageQuality
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.messages import build_openai_messages
from app.infrastructure.ai.model_pool import parse_model_pool, rotate_from
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
    """NVIDIA NIM API Adapter — Nemotron/Llama text pool RR + vision."""

    BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        default_model: Union[str, List[str]] = "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        vision_model: str = "meta/llama-3.2-90b-vision-instruct",
        text_models: Optional[List[str]] = None,
        vision_models: Optional[List[str]] = None,
    ):
        self.api_key = api_key
        if text_models:
            self.text_models = [m for m in text_models if m]
        elif isinstance(default_model, list):
            self.text_models = [m for m in default_model if m]
        else:
            self.text_models = parse_model_pool(None, default_model)
        if not self.text_models:
            self.text_models = ["nvidia/llama-3.3-nemotron-super-49b-v1.5"]
        self.default_model = self.text_models[0]
        if vision_models:
            self.vision_models = [m for m in vision_models if m]
        else:
            self.vision_models = parse_model_pool(None, vision_model)
        if not self.vision_models:
            self.vision_models = ["meta/llama-3.2-90b-vision-instruct"]
        self.vision_model = self.vision_models[0]
        self._text_rr_index = 0
        self._vision_rr_index = 0

    def _next_text_order(self) -> List[str]:
        order = rotate_from(self.text_models, self._text_rr_index)
        self._text_rr_index += 1
        return order

    def _next_vision_order(self) -> List[str]:
        order = rotate_from(self.vision_models, self._vision_rr_index)
        self._vision_rr_index += 1
        return order

    async def _chat_once(
        self,
        model: str,
        messages: List[Dict],
        *,
        timeout: float = 20.0,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.BASE_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: NVIDIA NIM rate limit")
            if resp.status_code == 404:
                raise RuntimeError(f"404 NVIDIA model unavailable: {model}")
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        messages = build_openai_messages(prompt, system_prompt, history)
        last_error: Optional[Exception] = None
        for model in self._next_text_order():
            try:
                return await self._chat_once(model, messages)
            except Exception as exc:
                last_error = exc
                err = str(exc).lower()
                # Soft-fail to next model in pool on rate limit / missing model / HTTP errors
                if "429" in err or "404" in err or "rate limit" in err:
                    continue
                if "status" in err or "http" in err:
                    continue
                raise
        raise last_error or RuntimeError("NVIDIA text pool exhausted")

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
        """Multimodal claim vision via NVIDIA NIM VL pool (RR + failover)."""
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64_img}"
        instruction = build_vision_instruction(industry)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        last_error: Optional[Exception] = None
        for model in self._next_vision_order():
            try:
                raw = await self._chat_once(
                    model, messages, timeout=30.0, max_tokens=512, temperature=0.1
                )
                return _parse_vision_json(raw)
            except Exception as exc:
                last_error = exc
                err = str(exc).lower()
                if "429" in err or "404" in err or "rate limit" in err:
                    continue
                if "status" in err or "http" in err or "json" in err:
                    continue
                raise
        raise last_error or RuntimeError("NVIDIA vision pool exhausted")
