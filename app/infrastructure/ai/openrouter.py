import base64
import httpx
from typing import AsyncIterator, Dict, List, Optional
from app.core.config import settings
from app.domain.claims.models import ClaimVisionObservation
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.messages import build_openai_messages
from app.infrastructure.ai.model_pool import parse_model_pool, rotate_from
from app.infrastructure.ai.nvidia import _parse_vision_json
from app.infrastructure.ai.vision_prompts import build_vision_instruction


class OpenRouterProvider(AIProviderPort):
    """OpenRouter adapter — strong text + vision model pools with RR failover."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        vision_model: Optional[str] = None,
        text_model: Optional[str] = None,
        text_models: Optional[List[str]] = None,
        vision_models: Optional[List[str]] = None,
    ):
        self.api_key = api_key
        if text_models:
            self.text_models = [m for m in text_models if m]
        else:
            self.text_models = parse_model_pool(
                None,
                text_model
                or getattr(settings, "OPENROUTER_TEXT_MODEL", None)
                or "qwen/qwen-2.5-72b-instruct",
            )
        if not self.text_models:
            self.text_models = ["qwen/qwen-2.5-72b-instruct"]
        self.text_model = self.text_models[0]

        if vision_models:
            self.vision_models = [m for m in vision_models if m]
        else:
            self.vision_models = parse_model_pool(
                None,
                vision_model or settings.OPENROUTER_VISION_MODEL,
            )
        if not self.vision_models:
            self.vision_models = ["nvidia/nemotron-3.5-super-vl:free"]
        self.vision_model = self.vision_models[0]
        self._text_rr_index = 0
        self._vision_rr_index = 0

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional attribution headers (harmless if ignored)
            "HTTP-Referer": "https://chatbot-factory-yqa0.onrender.com",
            "X-Title": "Chatbot Factory Claim Vision",
        }

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
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.BASE_URL, json=payload, headers=self._headers())
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: OpenRouter rate limit")
            if resp.status_code == 404:
                raise RuntimeError(f"404 OpenRouter model unavailable: {model}")
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
                if "429" in err or "404" in err or "rate limit" in err:
                    continue
                if "status" in err or "http" in err:
                    continue
                raise
        raise last_error or RuntimeError("OpenRouter text pool exhausted")

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
        raise last_error or RuntimeError("OpenRouter vision pool exhausted")
