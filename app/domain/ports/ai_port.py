from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from app.domain.claims.models import ClaimVisionObservation


class AIProviderPort(ABC):
    """Abstract Port for AI model generation, streaming, and vision analysis."""

    @abstractmethod
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate full text response."""
        pass

    @abstractmethod
    def stream_text(self, prompt: str, system_prompt: Optional[str] = None) -> AsyncIterator[str]:
        """Stream tokens asynchronously."""
        pass

    @abstractmethod
    async def analyze_claim_image(self, image_bytes: bytes, mime_type: str) -> ClaimVisionObservation:
        """Analyze image and return structured observation only."""
        pass
