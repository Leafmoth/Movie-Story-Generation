from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class StoryGenerationRequest(BaseModel):
    logline: str = Field(..., min_length=1, description="用户输入的一句话概括")
    duration_minutes: int = Field(..., ge=1, le=600, description="影片时长，单位分钟")
    theme_question: Optional[str] = Field(default="", description="主题问题，可不填")
    genre: Optional[str] = Field(default="", description="影片类型，可不填，系统会自动补充")
    project_id: Optional[str] = Field(default=None, description="输出项目目录名，可不填")
    include_storyboard: bool = Field(default=True, description="是否在文学剧本后继续生成分镜表格")
    pass_score: int = Field(default=85, ge=0, le=100, description="评论家通过分数，预留给评论家迭代流程使用")
    character_detail_fields: List[str] = Field(
        default_factory=list,
        description="角色设置中由前端勾选追加生成的可选字段。",
    )
    max_critic_retries: int = Field(default=3, ge=0, le=10, description="大纲评论家未通过时最多自动重试次数。")
    workflow_mode: Literal["auto", "interactive"] = Field(
        default="auto",
        description="兼容旧前端的保留字段。/api/story-jobs 当前始终使用 interactive 阶段流程。",
    )
    confirm_stages: Optional[List[str]] = Field(
        default=None,
        description="interactive 模式下需要人工确认的阶段，不填使用默认确认点。",
    )


class StoryboardGenerationRequest(BaseModel):
    final_script: Optional[str] = Field(default=None, description="文学剧本文本，可直接传入")
    script_path: Optional[str] = Field(default=None, description="已有 final_script.md 的路径")
    project_id: Optional[str] = Field(default=None, description="outputs 下的项目目录名")
    output_dir: Optional[str] = Field(default=None, description="分镜表格保存目录，可不填")


class StoryGenerationResponse(BaseModel):
    project_id: str
    output_dir: str
    stage_files: Dict[str, str]
    logline: str
    world: str = ""
    characters: str
    character_relations: str
    relationship_graph: str = ""
    outline_critic: str = ""
    biography: str = Field(default="", description="旧字段。新版 /api/story-jobs 流程不再生成人物小传，默认为空。")
    outline: str
    final_script: str
    storyboard: str = ""


def response_from_state(state: dict) -> StoryGenerationResponse:
    return StoryGenerationResponse(
        project_id=state["project_id"],
        output_dir=state["output_dir"],
        stage_files=state.get("stage_files", {}),
        logline=state.get("logline", ""),
        world=state.get("world", ""),
        characters=state.get("characters", ""),
        character_relations=state.get("character_relations", ""),
        relationship_graph=state.get("relationship_graph", ""),
        outline_critic=state.get("outline_critic", ""),
        biography=state.get("biography", ""),
        outline=state.get("outline", ""),
        final_script=state.get("final_script", ""),
        storyboard=state.get("storyboard", ""),
    )
