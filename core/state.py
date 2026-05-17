from __future__ import annotations

from typing import Any, TypedDict


class ProjectState(TypedDict, total=False):
    project_id: str
    output_dir: str
    input_logline: str
    theme_question: str
    duration_minutes: int
    genre: str
    character_detail_fields: list[str]
    logline: str
    world: str
    characters: str
    character_relations: str
    relationship_graph: str
    biography: str
    outline: str
    outline_critic: str
    critic_reports: list[dict[str, Any]]
    final_script: str
    storyboard: str
    include_storyboard: bool
    stage_files: dict[str, str]
    metadata: dict[str, Any]
    revision_feedback: str
    revision_mode: str
