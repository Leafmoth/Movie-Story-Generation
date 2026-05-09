from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from config.settings import Settings


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, messages: Iterable[ChatMessage], *, stage_name: str) -> str:
        if self.settings.mock_llm:
            return self._mock_response(stage_name, messages)

        if not self.settings.deepseek_api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set. Add it to .env, or set MOCK_LLM=1 for a dry run."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError("Package 'openai' is missing. Run: pip install -r requirements.txt") from exc

        client = OpenAI(
            api_key=self.settings.deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
            timeout=self.settings.request_timeout,
        )
        payload = {
            "model": self.settings.model_name,
            "messages": [message.__dict__ for message in messages],
            "temperature": self.settings.temperature,
        }
        if self.settings.max_tokens is not None:
            payload["max_tokens"] = self.settings.max_tokens

        response = client.chat.completions.create(**payload)
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError(f"LLM returned empty content for stage: {stage_name}")
        return content.strip()

    @staticmethod
    def _mock_response(stage_name: str, messages: Iterable[ChatMessage]) -> str:
        user_prompt = list(messages)[-1].content
        preview = user_prompt[:240].replace("\n", "\\n")
        return json.dumps(
            {
                "mock": True,
                "stage": stage_name,
                "content": f"MOCK_LLM enabled. Prompt preview: {preview}",
            },
            ensure_ascii=False,
            indent=2,
        )
