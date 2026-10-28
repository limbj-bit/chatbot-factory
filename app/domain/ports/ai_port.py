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
