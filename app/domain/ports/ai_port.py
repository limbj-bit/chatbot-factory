from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional
from app.domain.claims.models import ClaimVisionObservation


class AIProviderPort(ABC):
    """Abstract Port for AI model generation, streaming, and vision analysis."""

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate full text response.

        `history` is the recent conversation as [{"role": "user"|"assistant",
        "content": str}, ...] (oldest first, current prompt EXCLUDED). Passing it
        enables multi-turn memory; providers map it to their native format.
        """
        pass

    async def translate_text(self, text: str, target_lang: str, source_lang: str = "auto") -> str:
        """Translate `text` into `target_lang` (ISO code or name).

        Default implementation delegates to generate_text with a strict
        translation prompt, so providers only override if they have a native
        translation endpoint. Returns the original text on failure.
        """
        if not text or not text.strip():
            return text
        lang_name = {"ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese"}.get(
            target_lang.lower(), target_lang
        )
        prompt = (
            f"Translate the following text into {lang_name}. "
            "Output ONLY the translation, no explanations, no quotes, "
            "preserve line breaks and meaning exactly.\n\n"
            f"{text}"
        )
        try:
            return (await self.generate_text(prompt)).strip()
        except Exception:
            return text

    @abstractmethod
    def stream_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        """Stream tokens asynchronously."""
        pass

    @abstractmethod
    async def analyze_claim_image(
        self, image_bytes: bytes, mime_type: str, industry: Optional[str] = None
    ) -> ClaimVisionObservation:
        """Analyze image and return structured observation only.

        `industry` (optional) selects industry-specific vision guidance so the
        model focuses on the right defect vocabulary for that store category.
        """
        pass
