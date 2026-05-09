from __future__ import annotations

from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage, logline_postprocess
from core.storage import ProjectStorage


def make_logline_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="logline",
        prompt_file="logline_prompt.txt",
        output_key="logline",
        output_filename="01_logline.json",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        postprocess=logline_postprocess,
    )
