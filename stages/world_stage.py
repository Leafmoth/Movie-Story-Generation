from __future__ import annotations

from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.storage import ProjectStorage


def make_world_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="world",
        prompt_file="world_prompt.txt",
        output_key="world",
        output_filename="02_world.json",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={"Logline": "logline"},
    )
