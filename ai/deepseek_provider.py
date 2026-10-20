"""DeepSeek API provider (OpenAI-compatible REST client with deterministic fallback)."""

from __future__ import annotations

import json
from typing import Any

import requests

from ai.base_provider import BaseAIProvider
from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)


class DeepSeekAIProvider(BaseAIProvider):
    """DeepSeek API client (`deepseek-chat` / `deepseek-reasoner`)."""

    provider_name = "DEEPSEEK_API"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.deepseek_api_key
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model = model or settings.deepseek_model

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.is_available():
            return fallback_payload
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    parsed["generated_by"] = f"DEEPSEEK:{self.model}"
                    return parsed
        except Exception as exc:
            logger.warning("DeepSeek API call failed (%s); using deterministic fallback.", exc)
        return fallback_payload
