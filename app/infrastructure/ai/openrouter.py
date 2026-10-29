import base64
import httpx
from typing import AsyncIterator, Dict, List, Optional
from app.core.config import settings
from app.domain.claims.models import ClaimVisionObservation
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.messages import build_openai_messages
from app.infrastructure.ai.nvidia import _parse_vision_json
from app.infrastructure.ai.vision_prompts import build_vision_instruction


class OpenRouterProvider(AIProviderPort):
    """OpenRouter API Adapter (OpenAI-compatible) for multimodal vision backup.

    Gives access to many vision models (GPT-4o, Claude, Gemini, Qwen-VL, ...)
    through a single key, acting as a robust backup to the primary vision
    provider. Uses `OPENROUTER_VISION_MODEL` (default openai/gpt-4o-mini).
    """

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        vision_model: Optional[str] = None,
        text_model: Optional[str] = None,
    ):
        self.api_key = api_key
        self.vision_model = vision_model or settings.OPENROUTER_VISION_MODEL
        # Chat must NOT reuse the vision mini model — pick a dedicated text model.
        self.text_model = text_model or getattr(
            settings, "OPENROUTER_TEXT_MODEL", None
        ) or "qwen/qwen-2.5-72b-instruct"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional attribution headers (harmless if ignored)
            "HTTP-Referer": "https://chatbot-factory-yqa0.onrender.com",
            "X-Title": "Chatbot Factory Claim Vision",
        }

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        messages = build_openai_messages(prompt, system_prompt, history)

        payload = {
            "model": self.text_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(self.BASE_URL, json=payload, headers=self._headers())
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: OpenRouter rate limit")
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

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
            resp = await client.post(self.BASE_URL, json=payload, headers=self._headers())
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: OpenRouter rate limit")
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            return _parse_vision_json(raw)
