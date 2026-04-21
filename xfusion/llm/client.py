from __future__ import annotations

import httpx

from xfusion.app.settings import Settings


class LLMClient:
    """OpenAI-compatible LLM client for XFusion Guardian."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete(self, system_prompt: str, user_prompt: str, timeout: float = 20.0) -> str:
        if (
            not self.settings.llm_base_url
            or not self.settings.llm_api_key
            or not self.settings.llm_model
        ):
            # Fallback to deterministic mocks if LLM is not configured
            # In a real production system, this might raise an error or use a local model.
            return self._mock_fallback(user_prompt)

        body = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }

        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"

        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()

        return str(data["choices"][0]["message"]["content"])

    def _mock_fallback(self, user_prompt: str) -> str:
        """Deterministic mock fallback for development without LLM keys."""
        prompt = user_prompt.lower()
        if "disk" in prompt:
            return "CHECK_DISK_USAGE"
        if "process" in prompt or "port" in prompt:
            return "FIND_PROCESS_BY_PORT"
        if "user" in prompt:
            return "CREATE_USER"
        return "UNKNOWN_INTENT"
