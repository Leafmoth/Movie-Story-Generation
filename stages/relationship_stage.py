from __future__ import annotations

from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.storage import ProjectStorage


def make_relationship_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="relationships",
        prompt_file="relationship_prompt.txt",
        output_key="character_relations",
        output_filename="03_relationships.json",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={"Logline": "logline", "characters": "characters"},
    )
