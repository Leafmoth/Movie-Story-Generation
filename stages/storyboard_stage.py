from __future__ import annotations

from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.storage import ProjectStorage


def make_storyboard_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="storyboard",
        prompt_file="storyboard_prompt.txt",
        output_key="storyboard",
        output_filename="06_storyboard.csv",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={"scene_write": "final_script"},
        system_prompt="你是一名从业数十年的顶级电影导演。严格遵守用户给定提示词，不改变原意。",
    )
