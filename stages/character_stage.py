from __future__ import annotations

from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.storage import ProjectStorage


def make_character_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="characters",
        prompt_file="character_prompt.txt",
        output_key="characters",
        output_filename="02_characters.json",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={"Logline": "logline"},
    )
