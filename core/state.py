from __future__ import annotations

from typing import Any, TypedDict


class ProjectState(TypedDict, total=False):
    project_id: str
    output_dir: str
    input_logline: str
    theme_question: str
    duration_minutes: int
    genre: str
    logline: str
    characters: str
    character_relations: str
    biography: str
    outline: str
    final_script: str
    storyboard: str
    include_storyboard: bool
    stage_files: dict[str, str]
    metadata: dict[str, Any]
