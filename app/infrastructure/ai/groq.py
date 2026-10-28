import httpx
from typing import AsyncIterator, Optional
from app.domain.claims.models import ClaimVisionObservation
from app.domain.ports.ai_port import AIProviderPort


class GroqProvider(AIProviderPort):
    """Groq API Adapter for high-speed low-latency text generation and CS conversations."""

    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, default_model: str = "llama-3.3-70b-versatile"):
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
            "temperature": 0.3,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.BASE_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                raise RuntimeError("429 Too Many Requests: Groq rate limit")
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream_text(self, prompt: str, system_prompt: Optional[str] = None) -> AsyncIterator[str]:
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
            "temperature": 0.3,
            "max_tokens": 1024,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            async with client.stream("POST", self.BASE_URL, json=payload, headers=headers) as response:
                if response.status_code == 429:
                    raise RuntimeError("429 Too Many Requests: Groq rate limit")
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            import json
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue

    async def analyze_claim_image(self, image_bytes: bytes, mime_type: str) -> ClaimVisionObservation:
        raise NotImplementedError("GroqProvider is used for fast text CS; vision routed to Gemini/NVIDIA.")
