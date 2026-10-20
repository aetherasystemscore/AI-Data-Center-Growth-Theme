"""Local Ollama / Deterministic Rule-Based AI Provider (runs 100% offline with zero API keys)."""

from __future__ import annotations

import json
from typing import Any

import requests

from ai.base_provider import BaseAIProvider
from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)


class LocalRuleAndOllamaProvider(BaseAIProvider):
    """Uses local Ollama if configured, or deterministic rule-based extraction & synthesis."""

    provider_name = "DETERMINISTIC_RULE_ENGINE"

    def __init__(self, use_ollama: bool = False) -> None:
        self.settings = get_settings()
        self.use_ollama = use_ollama

    def is_available(self) -> bool:
        return True

    def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.use_ollama:
            try:
                resp = requests.post(
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/generate",
                    json={
                        "model": self.settings.ollama_model,
                        "prompt": f"{system_prompt}\n\n{user_prompt}",
                        "format": "json",
                        "stream": False,
                    },
                    timeout=8,
                )
                if resp.status_code == 200:
                    parsed = json.loads(resp.json().get("response", "{}"))
                    if isinstance(parsed, dict) and parsed:
                        parsed["generated_by"] = f"OLLAMA:{self.settings.ollama_model}"
                        return parsed
            except Exception as exc:
                logger.debug("Local Ollama not reachable (%s); returning deterministic payload.", exc)

        out = dict(fallback_payload)
        out.setdefault("generated_by", "DETERMINISTIC_RULE_ENGINE")
        return out
