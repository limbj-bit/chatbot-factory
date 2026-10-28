import httpx
from typing import AsyncIterator, Optional
from app.domain.claims.models import ClaimVisionObservation
from app.domain.ports.ai_port import AIProviderPort


class NvidiaProvider(AIProviderPort):
    """NVIDIA NIM API Adapter for complex reasoning, classification, and fallback."""

    BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

    def __init__(self, api_key: str, default_model: str = "meta/llama-3.1-70b-instruct"):
        self.api_key = api_key
        self.default_model = default_model

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

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

    async def stream_text(self, prompt: str, system_prompt: Optional[str] = None) -> AsyncIterator[str]:
        # Simple streaming fallback or direct full-text yield
        full_text = await self.generate_text(prompt, system_prompt)
        words = full_text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    async def analyze_claim_image(self, image_bytes: bytes, mime_type: str) -> ClaimVisionObservation:
        raise NotImplementedError("NVIDIA NIM vision model adapter configured via multimodal endpoint.")
