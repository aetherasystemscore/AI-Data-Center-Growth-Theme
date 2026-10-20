"""Google Gemini API provider with deterministic fallback."""

from __future__ import annotations

import json
from typing import Any

import requests

from ai.base_provider import BaseAIProvider
from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)


class GeminiAIProvider(BaseAIProvider):
    """Google Gemini REST API client (`gemini-2.5-flash` / `gemini-2.5-pro`)."""

    provider_name = "GEMINI_API"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model

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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=15,
            )
            if resp.status_code == 200:
                candidates = resp.json().get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"]
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        parsed["generated_by"] = f"GEMINI:{self.model}"
                        return parsed
        except Exception as exc:
            logger.warning("Gemini API call failed (%s); using deterministic fallback.", exc)
        return fallback_payload
