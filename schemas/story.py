from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


class StoryGenerationRequest(BaseModel):
    logline: str = Field(..., min_length=1, description="用户输入的一句话概括")
    duration_minutes: int = Field(..., ge=1, le=600, description="影片时长，单位分钟")
    theme_question: Optional[str] = Field(default="", description="主题问题，可不填")
    genre: Optional[str] = Field(default="", description="影片类型，可不填，系统会自动补充")
    project_id: Optional[str] = Field(default=None, description="输出项目目录名，可不填")


class StoryGenerationResponse(BaseModel):
    project_id: str
    output_dir: str
    stage_files: Dict[str, str]
    logline: str
    characters: str
    character_relations: str
    biography: str
    outline: str
    final_script: str


def response_from_state(state: dict) -> StoryGenerationResponse:
    return StoryGenerationResponse(
        project_id=state["project_id"],
        output_dir=state["output_dir"],
        stage_files=state.get("stage_files", {}),
        logline=state.get("logline", ""),
        characters=state.get("characters", ""),
        character_relations=state.get("character_relations", ""),
        biography=state.get("biography", ""),
        outline=state.get("outline", ""),
        final_script=state.get("final_script", ""),
    )
