from __future__ import annotations

from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.storage import ProjectStorage


def make_biography_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="biography",
        prompt_file="biography_prompt.txt",
        output_key="biography",
        output_filename="04_biography.json",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={
            "Logline": "logline",
            "characters": "characters",
            "character_relations": "character_relations",
        },
    )
