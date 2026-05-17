from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Iterable

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

    def generate_stream(
        self,
        messages: Iterable[ChatMessage],
        *,
        stage_name: str,
        on_token: Callable[[str], None],
    ) -> str:
        message_list = list(messages)
        if self.settings.mock_llm:
            content = self._mock_response(stage_name, message_list)
            for index in range(0, len(content), 12):
                token = content[index : index + 12]
                if token:
                    on_token(token)
            return content.strip()

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
            "messages": [message.__dict__ for message in message_list],
            "temperature": self.settings.temperature,
            "stream": True,
        }
        if self.settings.max_tokens is not None:
            payload["max_tokens"] = self.settings.max_tokens

        chunks: list[str] = []
        for chunk in client.chat.completions.create(**payload):
            delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else ""
            if not delta:
                continue
            chunks.append(delta)
            on_token(delta)

        content = "".join(chunks).strip()
        if not content:
            raise RuntimeError(f"LLM returned empty content for stage: {stage_name}")
        return content

    @staticmethod
    def _mock_response(stage_name: str, messages: Iterable[ChatMessage]) -> str:
        user_prompt = list(messages)[-1].content
        preview = user_prompt[:240].replace("\n", "\\n")
        if stage_name == "relationship_graph":
            return json.dumps(
                {
                    "relationship_graph": [
                        {"source": "主角", "target": "对手", "relationship": "核心冲突"},
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
        if stage_name == "outline_critic":
            return json.dumps(
                {
                    "score": 95,
                    "passed": True,
                    "issues": [],
                    "revision_advice": "",
                },
                ensure_ascii=False,
                indent=2,
            )
        if stage_name == "scene_write_chunk":
            return json.dumps(
                {
                    "act": 1,
                    "scene": "mock",
                    "title": "Mock 场次",
                    "estimated_duration_minutes": 1,
                    "script_text": "【1】. 内景. Mock 房间 - 日\n本场预计时长：1分钟\n角色A：这是一句测试对白。\n角色B：我接住上一场的情绪。",
                    "continuity_notes": "测试场次结束，人物关系继续推进。",
                    "constraint_check": ["MOCK_LLM enabled"],
                },
                ensure_ascii=False,
                indent=2,
            )
        if stage_name == "scene_write_critic":
            return json.dumps(
                {
                    "passed": True,
                    "issues": [],
                    "revision_advice": "",
                },
                ensure_ascii=False,
                indent=2,
            )
        if stage_name == "storyboard_chunk":
            return json.dumps(
                [
                    {
                        "镜头类型/景别": "中景",
                        "画面内容": "角色A开口说话，角色B倾听。",
                        "人物调度": "两人面对面",
                        "摄影机角度": "平视",
                        "摄影机运动": "固定",
                        "声音/对白": "这是一句测试对白。我接住上一场的情绪。",
                        "剪辑/转场": "切至",
                        "时长": "30秒",
                        "镜头目的": "覆盖测试对白",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            )
        return json.dumps(
            {
                "mock": True,
                "stage": stage_name,
                "content": f"MOCK_LLM enabled. Prompt preview: {preview}",
            },
            ensure_ascii=False,
            indent=2,
        )
