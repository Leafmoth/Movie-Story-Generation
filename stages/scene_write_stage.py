from __future__ import annotations

from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.storage import ProjectStorage


def make_scene_write_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="scene_write",
        prompt_file="scene_write_prompt.txt",
        output_key="final_script",
        output_filename="final_script.md",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={"outline": "outline"},
    )
