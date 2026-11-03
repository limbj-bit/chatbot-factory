import httpx
from typing import AsyncIterator, Dict, List, Optional
from app.domain.claims.models import ClaimVisionObservation
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.messages import build_openai_messages


class MistralProvider(AIProviderPort):
    """Mistral AI API Adapter for high-accuracy reasoning, summarization, and multilingual A/S."""

    BASE_URL = "https://api.mistral.ai/v1/chat/completions"

    def __init__(self, api_key: str, default_model: str = "mistral-large-latest"):
        self.api_key = api_key
        self.default_model = default_model

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
                raise RuntimeError("429 Too Many Requests: Mistral rate limit")
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        """Real SSE streaming from Mistral (was buffering the full answer)."""
        import json

        messages = build_openai_messages(prompt, system_prompt, history)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.default_model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1024,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST", self.BASE_URL, json=payload, headers=headers
            ) as response:
                if response.status_code == 429:
                    raise RuntimeError("429 Too Many Requests: Mistral rate limit")
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {}).get("content") or ""
                    except Exception:
                        continue
                    if delta:
                        yield delta

    async def analyze_claim_image(
        self, image_bytes: bytes, mime_type: str, industry: Optional[str] = None
    ) -> ClaimVisionObservation:
        raise NotImplementedError("Mistral text models delegated; vision handled by multimodal models.")
