from __future__ import annotations

from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.storage import ProjectStorage


def make_relationship_graph_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="relationship_graph",
        prompt_file="relationship_graph_prompt.txt",
        output_key="relationship_graph",
        output_filename="03_relationship_graph.json",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={
            "characters": "characters",
            "character_relations": "character_relations",
        },
    )
