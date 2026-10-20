"""Abstract base AI provider interface and deterministic fallback engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAIProvider(ABC):
    """Unified interface for LLM providers and the deterministic offline fallback engine."""

    provider_name: str = "BASE"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and ready."""

    @abstractmethod
    def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a JSON dictionary adhering to the requested schema or return `fallback_payload`."""
