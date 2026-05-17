from __future__ import annotations

from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.storage import ProjectStorage


def make_outline_critic_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="outline_critic",
        prompt_file="critic_prompt.txt",
        output_key="outline_critic",
        output_filename="05_outline_critic.json",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={
            "Logline": "logline",
            "world": "world",
            "characters": "characters",
            "character_relations": "character_relations",
            "outline": "outline",
            "duration_minutes": "duration_minutes",
        },
        system_prompt="你是评论家，只输出严格 JSON，不输出 Markdown 或解释。",
    )
