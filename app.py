from __future__ import annotations

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.orchestrator import StoryOrchestrator
from core.storage import parse_json_object
from schemas.story import StoryboardGenerationRequest, StoryGenerationRequest, StoryGenerationResponse, response_from_state


app = FastAPI(title="Movie Story Generation", version="0.1.0")
orchestrator = StoryOrchestrator()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(orchestrator.settings.cors_allow_origins),
    allow_credentials=orchestrator.settings.cors_allow_credentials,
    allow_methods=list(orchestrator.settings.cors_allow_methods),
    allow_headers=list(orchestrator.settings.cors_allow_headers),
)

JobStatus = Literal["pending", "running", "waiting_confirmation", "succeeded", "failed", "cancelled"]
WorkflowMode = Literal["auto", "interactive"]
ConfirmationAction = Literal["approve", "revise"]
RevisionMode = Literal["modify", "rewrite"]


class StoryJobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str
    result_url: str
    replaced_job_id: Optional[str] = None


class StoryJobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    project_id: Optional[str] = None
    error: Optional[str] = None
    result_url: str
    files: Dict[str, str] = Field(default_factory=dict)
    workflow_mode: WorkflowMode = "auto"
    current_stage: Optional[str] = None
    pending_confirmation: Optional[Dict[str, Any]] = None
    confirmed_stages: list[str] = Field(default_factory=list)
    revision_counts: Dict[str, int] = Field(default_factory=dict)
    available_sections: list[str] = Field(default_factory=list)
    pass_score: int = 85
    max_critic_retries: int = 3
    cancel_requested: bool = False
    replaced_by_job_id: Optional[str] = None
    critic_reports: list[dict[str, Any]] = Field(default_factory=list)


class StoryJobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    result: Optional[StoryGenerationResponse] = None
    error: Optional[str] = None


class CharactersResponse(BaseModel):
    job_id: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[JobStatus] = None
    characters: str
    display_text: str
    parsed: Any = None
    file_url: Optional[str] = None


class StageSectionResponse(BaseModel):
    job_id: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[JobStatus] = None
    section: str
    content: str
    display_text: str
    parsed: Any = None
    file_url: Optional[str] = None
    relationships: Optional[str] = None
    relationship_graph: Optional[str] = None
    biography: Optional[str] = None
    outline: Optional[str] = None
    outline_critic: Optional[str] = None


class StageContentResponse(BaseModel):
    job_id: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[JobStatus] = None
    section: str
    content: str
    display_text: str
    parsed: Any = None
    file_url: Optional[str] = None


class StageContentUpdateRequest(BaseModel):
    content: str
    invalidate_downstream: bool = True
    note: str = ""


class ScriptSegmentsResponse(BaseModel):
    job_id: str
    status: JobStatus
    current_stage: Optional[str] = None
    progress: Dict[str, Any] = Field(default_factory=dict)
    segments: list[dict[str, Any]] = Field(default_factory=list)
    content: str = ""
    display_text: str = ""


class StoryJobConfirmationRequest(BaseModel):
    stage: str
    action: ConfirmationAction
    feedback: str = ""
    content: Optional[str] = None
    revision_mode: Optional[RevisionMode] = None


class StoryJobRegenerateRequest(BaseModel):
    logline: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    theme_question: Optional[str] = None
    genre: Optional[str] = None
    project_id: Optional[str] = None
    include_storyboard: Optional[bool] = None
    pass_score: Optional[int] = Field(default=None, ge=0, le=100)
    character_detail_fields: Optional[list[str]] = None
    max_critic_retries: Optional[int] = Field(default=None, ge=0, le=10)
    confirm_stages: Optional[list[str]] = None


class StoryJobRestartFromStageRequest(BaseModel):
    stage: str
    feedback: str = ""
    revision_mode: Optional[RevisionMode] = None


class StoryGenerationOptionsResponse(BaseModel):
    default_character_fields: dict[str, dict[str, list[str]]]
    optional_character_fields: dict[str, list[str]]
    default_max_critic_retries: int = 3
    default_pass_score: int = 85


job_executor = ThreadPoolExecutor(max_workers=2)
jobs_lock = Lock()
jobs: dict[str, dict[str, Any]] = {}

FILE_TYPE_ALIASES = {
    "logline": "logline",
    "world": "world",
    "characters": "characters",
    "character_relations": "character_relations",
    "relationships": "character_relations",
    "relationship_graph": "relationship_graph",
    "biography": "biography",
    "outline": "outline",
    "outline_critic": "outline_critic",
    "final_script": "final_script",
    "script": "final_script",
    "storyboard": "storyboard",
    "storyboard_xlsx": "storyboard",
    "workflow_state": "workflow_state",
    "revision_history": "revision_history",
}

FALLBACK_FILENAMES = {
    "logline": "01_logline.json",
    "world": "02_world.json",
    "characters": "02_characters.json",
    "character_relations": "03_relationships.json",
    "relationship_graph": "03_relationship_graph.json",
    "biography": "04_biography.json",
    "outline": "05_outline.json",
    "outline_critic": "05_outline_critic.json",
    "final_script": "final_script.md",
    "storyboard": "06_storyboard.xlsx",
    "workflow_state": "workflow_state.json",
    "revision_history": "revision_history.json",
}

STAGE_SECTION_KEYS = {
    "logline": "logline",
    "world": "world",
    "characters": "characters",
    "relationships": "character_relations",
    "relationship_graph": "relationship_graph",
    "biography": "biography",
    "outline": "outline",
    "outline_critic": "outline_critic",
    "final_script": "final_script",
    "storyboard": "storyboard",
}

STAGE_FILE_KEYS = {
    "logline": "logline",
    "world": "world",
    "characters": "characters",
    "relationships": "character_relations",
    "relationship_graph": "relationship_graph",
    "biography": "biography",
    "outline": "outline",
    "outline_critic": "outline_critic",
    "final_script": "final_script",
    "storyboard": "storyboard",
}

DEFAULT_CONFIRM_STAGES = ["logline", "world", "characters", "relationships", "outline", "final_script"]
INTERACTIVE_STAGE_ORDER = [
    "logline",
    "world",
    "characters",
    "relationships",
    "relationship_graph",
    "outline",
    "final_script",
    "storyboard",
]
CONFIRMABLE_STAGES = {
    "logline",
    "world",
    "characters",
    "relationships",
    "relationship_graph",
    "outline",
    "final_script",
    "storyboard",
}

DISPLAY_LABELS = {
    "characters": "角色设置",
    "world": "世界观设定",
    "setting": "时间地点与社会背景",
    "rules": "世界规则",
    "tone": "叙事基调",
    "conflict_system": "冲突机制",
    "constraints": "创作约束",
    "protagonist": "主角",
    "antagonist": "对手",
    "emotional_core": "情感核心人物",
    "ally": "盟友",
    "mirror": "镜像人物",
    "relationships": "人物关系",
    "name": "关系名称",
    "surface_relation": "表面关系",
    "a_wants_from_b": "A 想从 B 那里得到",
    "b_wants_from_a": "B 想从 A 那里得到",
    "conflict": "冲突",
    "hidden_thing": "隐藏的东西",
    "ending_change": "最后的变化",
    "protagonist_biography": "主角小传",
    "core_supporting_biographies": "核心配角小传",
    "functional_supporting_biographies": "功能性配角",
    "duration_minutes": "影片时长",
    "three_act_outline": "三幕式大纲",
    "act_1": "第一幕",
    "act_2": "第二幕",
    "act_3": "第三幕",
    "chapter_outline": "章节细纲",
    "chapter": "章节",
    "act": "所属幕",
    "summary": "内容概要",
    "relationship_graph": "人物关系图",
    "source": "角色 A",
    "target": "角色 B",
    "relationship": "关系概括",
    "external": "外部",
    "physiological": "生理维度",
    "psychological": "心理维度",
    "social": "社会维度",
    "internal": "内部",
    "score": "评分",
    "passed": "是否通过",
    "issues": "问题",
    "revision_advice": "修改建议",
}

DEFAULT_CHARACTER_FIELDS = {
    "external": {
        "physiological": ["姓名", "身高", "体重", "年龄", "外貌"],
        "psychological": ["感情生活", "道德标准", "情商智商"],
    },
    "internal": {
        "core": ["人物创伤", "人物缺陷", "人物性格", "人物选择", "人物动机"],
    },
}

OPTIONAL_CHARACTER_FIELDS = {
    "external_social": ["社会阶层", "职业", "教育程度", "家庭", "宗教信仰"],
    "internal": ["人物相信的谎言", "人物欲望", "人物弧光"],
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/story-generation-options", response_model=StoryGenerationOptionsResponse)
def get_story_generation_options() -> StoryGenerationOptionsResponse:
    return StoryGenerationOptionsResponse(
        default_character_fields=DEFAULT_CHARACTER_FIELDS,
        optional_character_fields=OPTIONAL_CHARACTER_FIELDS,
        default_max_critic_retries=3,
        default_pass_score=85,
    )


@app.post("/api/story-jobs", response_model=StoryJobCreateResponse, status_code=202)
def create_story_job(request: StoryGenerationRequest) -> StoryJobCreateResponse:
    payload = _model_to_payload(request)
    return _create_story_job(payload)


@app.post("/api/story-jobs/{job_id}/interrupt-regenerate", response_model=StoryJobCreateResponse, status_code=202)
def interrupt_and_regenerate_story_job(
    job_id: str,
    request: Optional[StoryJobRegenerateRequest] = Body(default=None),
) -> StoryJobCreateResponse:
    old_job = _get_job(job_id)
    payload = dict(old_job.get("request") or {})
    if request is not None:
        overrides = {key: value for key, value in _model_to_payload(request).items() if value is not None}
        payload.update(overrides)

    new_job = _create_story_job(payload, replaced_job_id=job_id)
    cancel_event = old_job.get("cancel_event")
    if hasattr(cancel_event, "set"):
        cancel_event.set()

    future = old_job.get("future")
    if future is not None:
        future.cancel()

    _update_job(
        job_id,
        status="cancelled",
        cancel_requested=True,
        pending_confirmation=None,
        replaced_by_job_id=new_job.job_id,
        error=None,
    )
    _persist_workflow_files(job_id)
    return new_job


@app.post("/api/story-jobs/{job_id}/restart-from-stage", response_model=StoryJobStatusResponse)
def restart_story_job_from_stage(
    job_id: str,
    request: StoryJobRestartFromStageRequest,
) -> StoryJobStatusResponse:
    job = _get_job(job_id)
    if job["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Job is running. Wait until it pauses or finishes before restarting from a stage.",
        )

    stage = request.stage.strip()
    payload = job.get("request") or {}
    stage_order = _interactive_stage_order(payload)
    if stage not in stage_order:
        supported = ", ".join(stage_order)
        raise HTTPException(status_code=400, detail=f"Unsupported restart stage. Supported stages: {supported}")

    state = dict(job.get("result_state") or {})
    if not state:
        raise HTTPException(status_code=409, detail="No generated state is available to restart from.")

    state = _invalidate_stage_and_downstream_state(state, stage)
    confirmed = _confirmed_without_downstream(job.get("confirmed_stages", []), stage)
    critic_reports = [] if _stage_invalidates_outline_critic(stage) else list(job.get("critic_reports", []))
    revision_counts = dict(job.get("revision_counts", {}))
    revision_counts[stage] = revision_counts.get(stage, 0) + 1

    _update_job(
        job_id,
        status="running",
        current_stage=stage,
        pending_confirmation=None,
        confirmed_stages=confirmed,
        revision_counts=revision_counts,
        critic_reports=critic_reports,
        result_state=state,
        available_sections=_available_sections_from_state(state),
        cancel_requested=False,
        cancel_event=Event(),
        error=None,
    )
    _append_revision_history(job_id, stage, "restart", request.feedback, request.revision_mode)
    _submit_interactive_job(
        job_id,
        payload,
        stage,
        request.feedback,
        request.revision_mode or "modify",
    )
    return _job_status_response(_get_job(job_id))


def _create_story_job(payload: dict[str, Any], *, replaced_job_id: str | None = None) -> StoryJobCreateResponse:
    job_id = uuid4().hex
    now = _now_iso()
    workflow_mode = "interactive"
    confirm_stages = _normalize_confirm_stages(payload.get("confirm_stages"))
    pass_score = int(payload.get("pass_score") if payload.get("pass_score") is not None else 85)
    max_critic_retries = int(
        payload.get("max_critic_retries") if payload.get("max_critic_retries") is not None else 3
    )
    cancel_event = Event()

    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "request": payload,
            "project_id": payload.get("project_id"),
            "result_state": None,
            "error": None,
            "workflow_mode": workflow_mode,
            "confirm_stages": confirm_stages,
            "pass_score": pass_score,
            "max_critic_retries": max_critic_retries,
            "current_stage": None,
            "pending_confirmation": None,
            "confirmed_stages": [],
            "revision_counts": {},
            "available_sections": [],
            "revision_history": [],
            "critic_reports": [],
            "cancel_requested": False,
            "cancel_event": cancel_event,
            "event_queue": Queue(maxsize=5000),
            "future": None,
            "replaced_by_job_id": None,
            "replaces_job_id": replaced_job_id,
        }

    _submit_interactive_job(job_id, payload, "logline", "")

    return StoryJobCreateResponse(
        job_id=job_id,
        status="pending",
        status_url=f"/api/story-jobs/{job_id}",
        result_url=f"/api/story-jobs/{job_id}/result",
        replaced_job_id=replaced_job_id,
    )


def _submit_interactive_job(
    job_id: str,
    payload: dict[str, Any],
    start_stage: str,
    feedback: str,
    revision_mode: str = "modify",
) -> None:
    future = job_executor.submit(_run_interactive_job, job_id, payload, start_stage, feedback, revision_mode)
    _update_job(job_id, future=future)


@app.get("/api/story-jobs/{job_id}", response_model=StoryJobStatusResponse)
def get_story_job(job_id: str) -> StoryJobStatusResponse:
    job = _get_job(job_id)
    return _job_status_response(job)


@app.get("/api/story-jobs/{job_id}/stream")
async def stream_story_job(job_id: str, request: Request) -> StreamingResponse:
    _get_job(job_id)
    return StreamingResponse(
        _story_job_event_stream(job_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/story-jobs/{job_id}/result", response_model=StoryJobResultResponse)
def get_story_job_result(job_id: str) -> StoryJobResultResponse:
    job = _get_job(job_id)
    result = None
    if job["status"] == "succeeded" and job.get("result_state"):
        result = response_from_state(job["result_state"])

    return StoryJobResultResponse(
        job_id=job["job_id"],
        status=job["status"],
        result=result,
        error=job.get("error"),
    )


@app.post("/api/story-jobs/{job_id}/confirm", response_model=StoryJobStatusResponse)
def confirm_story_job_stage(job_id: str, request: StoryJobConfirmationRequest) -> StoryJobStatusResponse:
    job = _get_job(job_id)
    if job.get("workflow_mode") != "interactive":
        raise HTTPException(status_code=400, detail="This job is not using interactive workflow mode.")
    if job["status"] != "waiting_confirmation":
        raise HTTPException(status_code=409, detail=f"Job is not waiting for confirmation: {job['status']}")

    stage = request.stage.strip()
    pending = job.get("pending_confirmation") or {}
    if stage != pending.get("stage"):
        raise HTTPException(status_code=409, detail=f"Pending confirmation stage is: {pending.get('stage')}")

    if request.action == "revise" and not request.feedback.strip():
        raise HTTPException(status_code=400, detail="feedback is required when action is revise.")
    if request.action == "revise" and stage == "logline" and request.revision_mode not in {"modify", "rewrite"}:
        raise HTTPException(status_code=400, detail="revision_mode is required for logline revise: modify or rewrite.")

    if request.content is not None:
        _apply_stage_content(job_id, stage, request.content)

    _append_revision_history(job_id, stage, request.action, request.feedback, request.revision_mode)

    if request.action == "approve":
        confirmed = list(dict.fromkeys([*job.get("confirmed_stages", []), stage]))
        _update_job(
            job_id,
            status="running",
            pending_confirmation=None,
            confirmed_stages=confirmed,
            error=None,
        )
        next_stage = _next_interactive_stage(stage, job.get("request") or {})
        if next_stage is None:
            _complete_interactive_job(job_id)
        else:
            _submit_interactive_job(job_id, job.get("request") or {}, next_stage, "")
    else:
        revision_counts = dict(job.get("revision_counts", {}))
        revision_counts[stage] = revision_counts.get(stage, 0) + 1
        confirmed = _confirmed_without_downstream(job.get("confirmed_stages", []), stage)
        critic_reports = [] if _stage_invalidates_outline_critic(stage) else list(job.get("critic_reports", []))
        _update_job(
            job_id,
            status="running",
            pending_confirmation=None,
            revision_counts=revision_counts,
            confirmed_stages=confirmed,
            critic_reports=critic_reports,
            error=None,
        )
        _submit_interactive_job(
            job_id,
            job.get("request") or {},
            stage,
            request.feedback,
            request.revision_mode or "modify",
        )

    return _job_status_response(_get_job(job_id))


@app.get("/api/story-jobs/{job_id}/stages/{stage}", response_model=StageContentResponse)
def get_story_job_stage(job_id: str, stage: str) -> StageContentResponse:
    job = _get_job(job_id)
    state = job.get("result_state") or {}
    return _stage_content_response_from_state(
        state,
        stage,
        job_id=job["job_id"],
        project_id=state.get("project_id") or job.get("project_id"),
        status=job["status"],
        file_url=f"/api/story-jobs/{job['job_id']}/files/{_file_key_for_stage(stage)}",
    )


@app.get("/api/story-jobs/{job_id}/stages/final_script/segments", response_model=ScriptSegmentsResponse)
def get_story_job_script_segments(job_id: str) -> ScriptSegmentsResponse:
    job = _get_job(job_id)
    state = job.get("result_state") or {}
    content = str(state.get("final_script") or "")
    return ScriptSegmentsResponse(
        job_id=job["job_id"],
        status=job["status"],
        current_stage=job.get("current_stage"),
        progress=dict(state.get("script_segment_progress") or {}),
        segments=list(state.get("script_segments") or []),
        content=content,
        display_text=content.strip(),
    )


@app.patch("/api/story-jobs/{job_id}/stages/{stage}", response_model=StageContentResponse)
def update_story_job_stage(
    job_id: str,
    stage: str,
    request: StageContentUpdateRequest,
) -> StageContentResponse:
    job = _get_job(job_id)
    if job["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Job is running. Pause at this stage with confirm_stages before editing stage content.",
        )

    normalized_stage = stage.strip()
    if normalized_stage == "outline_critic":
        raise HTTPException(status_code=400, detail="outline_critic is generated by backend and is not editable.")

    updated_state = _apply_stage_content(
        job_id,
        normalized_stage,
        request.content,
        invalidate_downstream=request.invalidate_downstream,
    )
    if request.note.strip():
        _append_revision_history(job_id, normalized_stage, "edit", request.note.strip())

    return _stage_content_response_from_state(
        updated_state,
        normalized_stage,
        job_id=job["job_id"],
        project_id=updated_state.get("project_id") or job.get("project_id"),
        status=_get_job(job_id)["status"],
        file_url=f"/api/story-jobs/{job['job_id']}/files/{_file_key_for_stage(normalized_stage)}",
    )


@app.get("/api/story-jobs/{job_id}/characters", response_model=CharactersResponse)
def get_story_job_characters(job_id: str) -> CharactersResponse:
    job = _get_job(job_id)
    if job["status"] != "succeeded":
        raise HTTPException(status_code=409, detail=f"Job is not completed yet: {job['status']}")

    state = job.get("result_state") or {}
    return _characters_response_from_state(
        state,
        job_id=job["job_id"],
        project_id=state.get("project_id") or job.get("project_id"),
        status=job["status"],
        file_url=f"/api/story-jobs/{job['job_id']}/files/characters",
    )


@app.get("/api/projects/{project_id}/characters", response_model=CharactersResponse)
def get_project_characters(project_id: str) -> CharactersResponse:
    path = _resolve_project_file(project_id, "characters")
    if path is None:
        raise HTTPException(status_code=404, detail=f"Characters file not found for project: {project_id}")

    characters = path.read_text(encoding="utf-8")
    parsed = parse_json_object(characters)
    return CharactersResponse(
        project_id=project_id,
        characters=characters,
        display_text=_display_text_from_content(characters, "characters", parsed),
        parsed=parsed,
        file_url=f"/api/projects/{project_id}/characters",
    )


@app.get("/api/projects/{project_id}/world", response_model=StageContentResponse)
def get_project_world(project_id: str) -> StageContentResponse:
    path = _resolve_project_file(project_id, "world")
    if path is None:
        raise HTTPException(status_code=404, detail=f"World file not found for project: {project_id}")

    content = path.read_text(encoding="utf-8")
    return _build_stage_content_response(
        section="world",
        content=content,
        project_id=project_id,
        file_url=f"/api/projects/{project_id}/world",
    )


@app.get("/api/story-jobs/{job_id}/relationships", response_model=StageSectionResponse)
def get_story_job_relationships(job_id: str) -> StageSectionResponse:
    return _story_job_stage_section_response(job_id, "relationships")


@app.get("/api/projects/{project_id}/relationships", response_model=StageSectionResponse)
def get_project_relationships(project_id: str) -> StageSectionResponse:
    return _project_stage_section_response(project_id, "relationships")


@app.get("/api/story-jobs/{job_id}/relationship-graph", response_model=StageSectionResponse)
def get_story_job_relationship_graph(job_id: str) -> StageSectionResponse:
    return _story_job_stage_section_response(job_id, "relationship_graph")


@app.get("/api/projects/{project_id}/relationship-graph", response_model=StageSectionResponse)
def get_project_relationship_graph(project_id: str) -> StageSectionResponse:
    return _project_stage_section_response(project_id, "relationship_graph")


@app.get("/api/story-jobs/{job_id}/biography", response_model=StageSectionResponse)
def get_story_job_biography(job_id: str) -> StageSectionResponse:
    job = _get_job(job_id)
    state = job.get("result_state") or {}
    if not state.get("biography"):
        raise HTTPException(
            status_code=404,
            detail="Biography is deprecated for new story jobs. Use characters and relationships instead.",
        )
    return _story_job_stage_section_response(job_id, "biography")


@app.get("/api/projects/{project_id}/biography", response_model=StageSectionResponse)
def get_project_biography(project_id: str) -> StageSectionResponse:
    return _project_stage_section_response(project_id, "biography")


@app.get("/api/story-jobs/{job_id}/outline", response_model=StageSectionResponse)
def get_story_job_outline(job_id: str) -> StageSectionResponse:
    return _story_job_stage_section_response(job_id, "outline")


@app.get("/api/projects/{project_id}/outline", response_model=StageSectionResponse)
def get_project_outline(project_id: str) -> StageSectionResponse:
    return _project_stage_section_response(project_id, "outline")


@app.get("/api/story-jobs/{job_id}/files/{file_type}")
def download_story_job_file(job_id: str, file_type: str) -> FileResponse:
    job = _get_job(job_id)
    if job["status"] != "succeeded":
        raise HTTPException(status_code=409, detail=f"Job is not completed yet: {job['status']}")

    state = job.get("result_state") or {}
    file_key = FILE_TYPE_ALIASES.get(file_type)
    if file_key is None:
        supported = ", ".join(sorted(FILE_TYPE_ALIASES))
        raise HTTPException(status_code=400, detail=f"Unsupported file_type. Supported values: {supported}")

    file_path = _resolve_result_file(state, file_key)
    if file_path is None:
        raise HTTPException(status_code=404, detail=f"File is not available for type: {file_type}")

    media_type = _media_type_for(file_path)
    return FileResponse(path=file_path, filename=file_path.name, media_type=media_type)


@app.post("/generate", response_model=StoryGenerationResponse)
def generate_story(request: StoryGenerationRequest) -> StoryGenerationResponse:
    payload = _model_to_payload(request)

    try:
        state = orchestrator.generate(payload, include_storyboard=payload.get("include_storyboard", True))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return response_from_state(state)


@app.post("/generate/script-only", response_model=StoryGenerationResponse)
def generate_script_only(request: StoryGenerationRequest) -> StoryGenerationResponse:
    payload = _model_to_payload(request)

    try:
        state = orchestrator.generate(payload, include_storyboard=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return response_from_state(state)


@app.post("/storyboard", response_model=StoryGenerationResponse)
def generate_storyboard(request: StoryboardGenerationRequest) -> StoryGenerationResponse:
    payload = _model_to_payload(request)

    final_script = (payload.get("final_script") or "").strip()
    script_path = payload.get("script_path")
    project_id = payload.get("project_id")
    output_dir = payload.get("output_dir")

    try:
        if not final_script:
            if script_path:
                path = Path(script_path)
            elif project_id:
                path = orchestrator.settings.output_root / project_id / "final_script.md"
                script_path = str(path)
            else:
                raise ValueError("Provide final_script, script_path, or project_id.")

            if not path.exists():
                raise FileNotFoundError(f"final_script not found: {path}")
            final_script = path.read_text(encoding="utf-8")
            output_dir = output_dir or str(path.resolve().parent)

        state = orchestrator.generate_storyboard_from_script(
            final_script=final_script,
            project_id=project_id,
            output_dir=output_dir,
            final_script_path=script_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return response_from_state(state)


@app.on_event("shutdown")
def shutdown_job_executor() -> None:
    job_executor.shutdown(wait=False, cancel_futures=True)


def _run_story_job(job_id: str, payload: dict[str, Any]) -> None:
    _update_job(job_id, status="running", error=None)
    try:
        state = orchestrator.generate(payload, include_storyboard=payload.get("include_storyboard", True))
    except Exception as exc:
        _update_job(job_id, status="failed", error=str(exc))
        return

    _update_job(
        job_id,
        status="succeeded",
        project_id=state.get("project_id"),
        result_state=dict(state),
        available_sections=_available_sections_from_state(dict(state)),
        error=None,
    )


def _run_interactive_job(
    job_id: str,
    payload: dict[str, Any],
    start_stage: str,
    feedback: str,
    revision_mode: str = "modify",
) -> None:
    if _is_job_cancelled(job_id):
        return
    _update_job(job_id, status="running", current_stage=start_stage, pending_confirmation=None, error=None)
    try:
        job = _get_job(job_id)
        state = job.get("result_state")
        if not state:
            state = orchestrator.create_initial_state(payload, include_storyboard=payload.get("include_storyboard", True))
        else:
            state = dict(state)

        if feedback.strip():
            state = _invalidate_downstream_state(state, start_stage)

        confirm_stages = job.get("confirm_stages", DEFAULT_CONFIRM_STAGES)
        stage_order = _interactive_stage_order(payload)
        start_index = stage_order.index(start_stage)

        for index in range(start_index, len(stage_order)):
            if _is_job_cancelled(job_id):
                return
            stage = stage_order[index]
            stage_feedback = feedback if index == start_index else ""
            if stage == "outline":
                state, force_confirmation = _run_outline_with_critic(
                    job_id,
                    state,
                    feedback=stage_feedback,
                    revision_mode=revision_mode if index == start_index else "modify",
                )
                if force_confirmation:
                    _pause_for_confirmation(job_id, stage, state)
                    return
            elif stage == "final_script":
                state = _run_final_script_with_segment_updates(
                    job_id,
                    state,
                    feedback=stage_feedback,
                    revision_mode=revision_mode if index == start_index else "modify",
                )
                if _is_job_cancelled(job_id):
                    return
                _update_job_state_after_stage(job_id, stage, state)
            elif stage == "storyboard":
                state = _run_storyboard_with_duration_check(
                    job_id,
                    state,
                    feedback=stage_feedback,
                    revision_mode=revision_mode if index == start_index else "modify",
                )
                if _is_job_cancelled(job_id):
                    return
                _update_job_state_after_stage(job_id, stage, state)
            else:
                state = _run_stage_with_token_stream(
                    job_id,
                    state,
                    _runner_stage_name(stage),
                    feedback=stage_feedback,
                    revision_mode=revision_mode if index == start_index else "modify",
                    public_stage=stage,
                )
                if _is_job_cancelled(job_id):
                    return
                _update_job_state_after_stage(job_id, stage, state)

            if stage in confirm_stages:
                _pause_for_confirmation(job_id, stage, state)
                return

        _finish_interactive_job(job_id, state)
    except Exception as exc:
        if _is_job_cancelled(job_id):
            return
        _update_job(job_id, status="failed", error=str(exc), pending_confirmation=None)


def _run_outline_with_critic(
    job_id: str,
    state: dict[str, Any],
    *,
    feedback: str = "",
    revision_mode: str = "modify",
) -> tuple[dict[str, Any], bool]:
    job = _get_job(job_id)
    pass_score = int(job.get("pass_score") if job.get("pass_score") is not None else 85)
    max_retries = int(job.get("max_critic_retries") if job.get("max_critic_retries") is not None else 3)
    reports = list(job.get("critic_reports", []))
    next_feedback = feedback
    next_revision_mode = revision_mode

    for attempt in range(max_retries + 1):
        if _is_job_cancelled(job_id):
            return state, False

        state = _run_stage_with_token_stream(
            job_id,
            state,
            "outline",
            feedback=next_feedback,
            revision_mode=next_revision_mode,
            public_stage="outline",
        )
        if _is_job_cancelled(job_id):
            return state, False
        _update_job_state_after_stage(job_id, "outline", state)

        state = orchestrator.run_stage(state, "outline_critic")
        parsed = parse_json_object(state.get("outline_critic") or "") or {}
        report = _normalize_critic_report(parsed, pass_score, attempt)
        report = _merge_duration_report(report, _outline_duration_report(state), pass_score)
        reports.append(report)
        state["critic_reports"] = reports
        _persist_critic_reports(state, reports)
        _update_job(job_id, critic_reports=reports)
        _update_job_state_after_stage(job_id, "outline_critic", state)

        if report.get("passed"):
            return state, False
        if attempt >= max_retries:
            return state, True

        next_feedback = str(report.get("revision_advice") or "请根据评论家指出的问题重写大纲。").strip()
        next_revision_mode = "modify"

    return state, True


def _normalize_critic_report(parsed: Any, pass_score: int, attempt: int) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {
            "attempt": attempt,
            "score": 0,
            "passed": False,
            "issues": ["评论家没有返回合法 JSON。"],
            "revision_advice": "请重新检查大纲与世界观、角色逻辑的一致性，并输出合法 JSON。",
            "raw": parsed,
        }

    score = _int_value(parsed.get("score"), 0)
    issues = parsed.get("issues")
    if not isinstance(issues, list):
        issues = [str(issues)] if issues else []
    passed = bool(parsed.get("passed")) and score >= pass_score and not issues
    return {
        "attempt": attempt,
        "score": score,
        "passed": passed,
        "issues": issues,
        "revision_advice": str(parsed.get("revision_advice") or "").strip(),
    }


def _run_stage_with_token_stream(
    job_id: str,
    state: dict[str, Any],
    stage_name: str,
    *,
    feedback: str = "",
    revision_mode: str = "modify",
    public_stage: str | None = None,
) -> dict[str, Any]:
    stage_state = dict(state)
    stage_state["llm_token_callback"] = _make_llm_token_callback(job_id, public_stage or stage_name)
    updated_state = orchestrator.run_stage(
        stage_state,
        stage_name,
        feedback=feedback,
        revision_mode=revision_mode,
    )
    updated_state.pop("llm_token_callback", None)
    return updated_state


def _run_final_script_with_segment_updates(
    job_id: str,
    state: dict[str, Any],
    *,
    feedback: str = "",
    revision_mode: str = "modify",
) -> dict[str, Any]:
    def on_segment(completed: int, total: int, segments: list[dict[str, Any]], content: str) -> None:
        if _is_job_cancelled(job_id):
            return
        partial_state = dict(_get_job(job_id).get("result_state") or state)
        partial_state["final_script"] = content
        partial_state["script_segments"] = segments
        partial_state["script_segment_progress"] = {
            "completed": completed,
            "total": total,
            "done": completed >= total,
        }
        output_dir = partial_state.get("output_dir")
        if output_dir:
            stage_files = dict(partial_state.get("stage_files", {}))
            saved_path = orchestrator.storage.save_stage(output_dir, FALLBACK_FILENAMES["final_script"], content)
            stage_files["final_script"] = saved_path
            partial_state["stage_files"] = stage_files
        _update_job(
            job_id,
            current_stage="final_script",
            result_state=partial_state,
            project_id=partial_state.get("project_id"),
            available_sections=_available_sections_from_state(partial_state),
        )
        _persist_workflow_files(job_id)

    stage_state = dict(state)
    stage_state["script_segment_callback"] = on_segment
    stage_state["llm_token_callback"] = _make_llm_token_callback(job_id, "final_script")
    updated_state = orchestrator.run_stage(
        stage_state,
        "final_script",
        feedback=feedback,
        revision_mode=revision_mode,
    )
    updated_state.pop("script_segment_callback", None)
    updated_state.pop("llm_token_callback", None)
    segment_count = len(updated_state.get("script_segments") or [])
    updated_state["script_segment_progress"] = {
        "completed": segment_count,
        "total": segment_count,
        "done": True,
    }
    return updated_state


def _merge_duration_report(
    critic_report: dict[str, Any],
    duration_report: dict[str, Any],
    pass_score: int,
) -> dict[str, Any]:
    merged = dict(critic_report)
    merged["duration_check"] = duration_report.get("summary", {})
    if duration_report.get("passed"):
        return merged

    issues = list(merged.get("issues") or [])
    issues.extend(str(item) for item in duration_report.get("issues", []) if str(item).strip())
    merged["issues"] = issues
    merged["passed"] = False
    merged["score"] = min(_int_value(merged.get("score"), 0), max(0, min(pass_score - 1, 75)))

    advice_parts = [
        str(merged.get("revision_advice") or "").strip(),
        str(duration_report.get("revision_advice") or "").strip(),
    ]
    merged["revision_advice"] = "\n".join(part for part in advice_parts if part)
    return merged


def _outline_duration_report(state: dict[str, Any]) -> dict[str, Any]:
    target = _target_duration_minutes(state)
    tolerance = _duration_tolerance_minutes(target)
    parsed = parse_json_object(state.get("outline") or "")
    issues: list[str] = []

    if target <= 0:
        return _duration_report(True, [], "", {"target_minutes": target, "tolerance_minutes": tolerance})

    if not isinstance(parsed, dict):
        return _duration_report(
            False,
            ["大纲没有返回可解析 JSON，无法校验章节时长。"],
            _outline_duration_revision_advice(target),
            {"target_minutes": target, "tolerance_minutes": tolerance},
        )

    top_duration = _duration_minutes_from_value(parsed.get("duration_minutes"))
    if top_duration is None:
        issues.append("大纲顶层缺少数字 duration_minutes。")
    elif abs(top_duration - target) > 0.01:
        issues.append(f"大纲顶层 duration_minutes 为 {top_duration:g}，目标为 {target:g}。")

    chapters = parsed.get("chapter_outline") or parsed.get("chapters") or parsed.get("章节细纲")
    if not isinstance(chapters, list) or not chapters:
        return _duration_report(
            False,
            issues + ["大纲缺少 chapter_outline 章节数组，无法建立时长预算。"],
            _outline_duration_revision_advice(target),
            {"target_minutes": target, "tolerance_minutes": tolerance},
        )

    chapter_minutes: list[float] = []
    missing_duration = 0
    act_minutes = {"act_1": 0.0, "act_2": 0.0, "act_3": 0.0}
    mapped_act_count = 0
    for index, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            missing_duration += 1
            continue
        minutes = _duration_minutes_from_value(chapter.get("duration_minutes"))
        if minutes is None:
            missing_duration += 1
            issues.append(f"第 {index} 个章节缺少数字 duration_minutes。")
            continue
        chapter_minutes.append(minutes)

        act_key = _act_key_from_value(chapter.get("act"))
        if act_key:
            act_minutes[act_key] += minutes
            mapped_act_count += 1

    if missing_duration:
        issues.append(f"共有 {missing_duration} 个章节没有可解析的数字时长。")

    total = round(sum(chapter_minutes), 2)
    if not chapter_minutes:
        issues.append("所有章节都缺少有效时长，无法校验总片长。")
    elif abs(total - target) > 0.01:
        issues.append(f"章节时长总和为 {total:g} 分钟，目标为 {target:g} 分钟，必须精确相等。")

    if mapped_act_count == 0:
        issues.append("章节没有标明所属幕，无法校验三幕 25% / 50% / 25% 的时长比例。")
    else:
        expected = {"act_1": target * 0.25, "act_2": target * 0.5, "act_3": target * 0.25}
        for act_key, expected_minutes in expected.items():
            actual = act_minutes[act_key]
            if abs(actual - expected_minutes) > tolerance:
                label = {"act_1": "第一幕", "act_2": "第二幕", "act_3": "第三幕"}[act_key]
                issues.append(
                    f"{label}时长为 {actual:g} 分钟，目标约 {expected_minutes:g} 分钟，超过允许误差 {tolerance:g} 分钟。"
                )

    three_act = parsed.get("three_act_outline")
    if not isinstance(three_act, dict):
        issues.append("three_act_outline 缺少可解析的三幕对象，无法确认每幕数字时长。")
    else:
        expected = {"act_1": target * 0.25, "act_2": target * 0.5, "act_3": target * 0.25}
        for act_key, expected_minutes in expected.items():
            act_value = three_act.get(act_key)
            act_duration = _duration_minutes_from_value(
                act_value.get("duration_minutes") if isinstance(act_value, dict) else act_value
            )
            if act_duration is None:
                issues.append(f"three_act_outline.{act_key} 缺少数字 duration_minutes。")
            elif abs(act_duration - expected_minutes) > tolerance:
                issues.append(
                    f"three_act_outline.{act_key}.duration_minutes 为 {act_duration:g}，目标约 {expected_minutes:g}。"
                )

    chapter_count = len(chapter_minutes)
    if target >= 60 and chapter_count < 6:
        issues.append("目标片长超过 60 分钟，但有效章节少于 6 个，单章承载过重，后续剧本和分镜难以控制时长。")
    elif 20 <= target < 60 and chapter_count < 4:
        issues.append("目标片长超过 20 分钟，但有效章节少于 4 个，章节数量不足以支撑片长控制。")

    summary = {
        "target_minutes": target,
        "total_chapter_minutes": total,
        "tolerance_minutes": tolerance,
        "act_minutes": {key: round(value, 2) for key, value in act_minutes.items()},
        "chapter_count": chapter_count,
    }
    return _duration_report(not issues, issues, _outline_duration_revision_advice(target), summary)


def _run_storyboard_with_duration_check(
    job_id: str,
    state: dict[str, Any],
    *,
    feedback: str = "",
    revision_mode: str = "modify",
) -> dict[str, Any]:
    job = _get_job(job_id)
    max_retries = int(job.get("max_critic_retries") if job.get("max_critic_retries") is not None else 3)
    reports = list(job.get("critic_reports", []))
    next_feedback = feedback
    next_revision_mode = revision_mode

    for attempt in range(max_retries + 1):
        if _is_job_cancelled(job_id):
            return state

        state = _run_stage_with_token_stream(
            job_id,
            state,
            "storyboard",
            feedback=next_feedback,
            revision_mode=next_revision_mode,
            public_stage="storyboard",
        )
        report = _storyboard_duration_report(state, attempt)
        reports.append(report)
        state["critic_reports"] = reports
        _persist_critic_reports(state, reports)
        _update_job(job_id, critic_reports=reports)

        if report.get("passed") or attempt >= max_retries:
            return state

        next_feedback = str(report.get("revision_advice") or "").strip()
        next_revision_mode = "modify"

    return state


def _storyboard_duration_report(state: dict[str, Any], attempt: int) -> dict[str, Any]:
    target = _target_duration_minutes(state)
    tolerance = _duration_tolerance_minutes(target)
    issues: list[str] = []

    try:
        from stages.storyboard_stage import HEADERS, normalize_storyboard_rows
    except Exception as exc:  # pragma: no cover - import should be stable in app runtime
        return {
            "stage": "storyboard_duration",
            "attempt": attempt,
            "score": 0,
            "passed": False,
            "issues": [f"无法加载分镜表解析器：{exc}"],
            "revision_advice": "请保持分镜为标准 CSV，并包含“时长”列。",
        }

    rows = normalize_storyboard_rows(str(state.get("storyboard") or ""))
    duration_index = HEADERS.index("时长")
    durations: list[float] = []
    missing_count = 0
    for row in rows[1:]:
        if not row or all(not str(cell).strip() for cell in row):
            continue
        cell = row[duration_index] if len(row) > duration_index else ""
        minutes = _storyboard_duration_cell_to_minutes(cell)
        if minutes is None:
            missing_count += 1
        else:
            durations.append(minutes)

    total = round(sum(durations), 2)
    if not durations:
        issues.append("分镜表“时长”列没有可解析的镜头时长。")
    elif abs(total - target) > tolerance:
        issues.append(f"分镜总时长为 {total:g} 分钟，目标为 {target:g} 分钟，超过允许误差 {tolerance:g} 分钟。")
    if missing_count:
        issues.append(f"分镜表中有 {missing_count} 条镜头缺少可解析时长。")

    advice = (
        f"请重写分镜表或调整镜头数量与“时长”列，使所有镜头时长总和接近 {target:g} 分钟，"
        f"允许误差不超过 {tolerance:g} 分钟。时长列建议使用“秒”为单位，例如 6秒、12秒、45秒。"
    )
    score = 100 if not issues else 70
    return {
        "stage": "storyboard_duration",
        "attempt": attempt,
        "score": score,
        "passed": not issues,
        "issues": issues,
        "revision_advice": "" if not issues else advice,
        "duration_check": {
            "target_minutes": target,
            "total_storyboard_minutes": total,
            "tolerance_minutes": tolerance,
            "parsed_shot_count": len(durations),
            "missing_duration_count": missing_count,
        },
    }


def _target_duration_minutes(state: dict[str, Any]) -> float:
    value = state.get("duration_minutes")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _duration_tolerance_minutes(target: float) -> float:
    return round(max(1.0, target * 0.05), 2)


def _duration_report(
    passed: bool,
    issues: list[str],
    revision_advice: str,
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "passed": passed,
        "issues": issues,
        "revision_advice": "" if passed else revision_advice,
        "summary": summary,
    }


def _outline_duration_revision_advice(target: float) -> str:
    tolerance = _duration_tolerance_minutes(target)
    return (
        f"请重写大纲的时长预算：duration_minutes 必须为 {target:g}；"
        f"three_act_outline 每一幕必须包含数字 duration_minutes；"
        f"chapter_outline 每个章节必须包含数字 duration_minutes，所有章节相加等于 {target:g} 分钟，"
        f"总和不能有误差；第一幕、第二幕、第三幕时长分别约为 25%、50%、25%，幕比例误差不超过 {tolerance:g} 分钟。"
    )


def _duration_minutes_from_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "%" in text:
        return None
    numbers = _numbers_from_text(text)
    if not numbers:
        return None
    if len(numbers) >= 2 and ("-" in text or "到" in text or "~" in text or "至" in text):
        return sum(numbers[:2]) / 2
    return numbers[0]


def _storyboard_duration_cell_to_minutes(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    clock_match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})", text)
    if clock_match:
        hours = float(clock_match.group(1) or 0)
        minutes = float(clock_match.group(2) or 0)
        seconds = float(clock_match.group(3) or 0)
        return hours * 60 + minutes + seconds / 60

    minute_seconds = re.search(r"(\d+(?:\.\d+)?)\s*(?:分|分钟|min|m)\s*(\d+(?:\.\d+)?)\s*(?:秒|s|sec)?", text)
    if minute_seconds:
        return float(minute_seconds.group(1)) + float(minute_seconds.group(2)) / 60

    numbers = _numbers_from_text(text)
    if not numbers:
        return None
    value_number = sum(numbers[:2]) / 2 if len(numbers) >= 2 and ("-" in text or "到" in text or "~" in text or "至" in text) else numbers[0]
    if any(unit in text for unit in ("小时", "hour", "hr")):
        return value_number * 60
    if any(unit in text for unit in ("分钟", "分", "min")):
        return value_number
    return value_number / 60


def _numbers_from_text(text: str) -> list[float]:
    return [float(match) for match in re.findall(r"\d+(?:\.\d+)?", text)]


def _act_key_from_value(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if any(token in text for token in ("act_1", "act 1", "第一", "一幕", "1")):
        return "act_1"
    if any(token in text for token in ("act_2", "act 2", "第二", "二幕", "2")):
        return "act_2"
    if any(token in text for token in ("act_3", "act 3", "第三", "三幕", "3")):
        return "act_3"
    return None


def _persist_critic_reports(state: dict[str, Any], reports: list[dict[str, Any]]) -> None:
    output_dir = state.get("output_dir")
    if not output_dir:
        return

    content = json.dumps({"critic_reports": reports}, ensure_ascii=False, indent=2)
    path = Path(output_dir) / FALLBACK_FILENAMES["outline_critic"]
    path.write_text(content, encoding="utf-8")
    stage_files = dict(state.get("stage_files", {}))
    stage_files["outline_critic"] = str(path.resolve())
    state["stage_files"] = stage_files
    state["outline_critic"] = content


def _update_job_state_after_stage(job_id: str, stage: str, state: dict[str, Any]) -> None:
    if _is_job_cancelled(job_id):
        return
    available_sections = _available_sections_from_state(state)
    _update_job(
        job_id,
        current_stage=stage,
        project_id=state.get("project_id"),
        result_state=dict(state),
        available_sections=available_sections,
    )
    _persist_workflow_files(job_id)


def _pause_for_confirmation(job_id: str, stage: str, state: dict[str, Any]) -> None:
    if _is_job_cancelled(job_id):
        return
    _update_job(
        job_id,
        status="waiting_confirmation",
        current_stage=stage,
        pending_confirmation={
            "stage": stage,
            "stage_url": f"/api/story-jobs/{job_id}/stages/{stage}",
            "actions": ["approve", "revise"],
        },
        result_state=dict(state),
        available_sections=_available_sections_from_state(state),
    )
    _persist_workflow_files(job_id)


def _finish_interactive_job(job_id: str, state: dict[str, Any]) -> None:
    if _is_job_cancelled(job_id):
        return
    _update_job(
        job_id,
        status="succeeded",
        current_stage=None,
        pending_confirmation=None,
        project_id=state.get("project_id"),
        result_state=dict(state),
        available_sections=_available_sections_from_state(state),
        error=None,
    )
    _persist_workflow_files(job_id)


def _complete_interactive_job(job_id: str) -> None:
    job = _get_job(job_id)
    state = job.get("result_state") or {}
    _finish_interactive_job(job_id, dict(state))


def _apply_stage_content(
    job_id: str,
    stage: str,
    content: str,
    *,
    invalidate_downstream: bool = False,
) -> dict[str, Any]:
    state = dict(_get_job(job_id).get("result_state") or {})
    state_key = STAGE_SECTION_KEYS.get(stage)
    file_key = STAGE_FILE_KEYS.get(stage)
    if state_key is None or file_key is None:
        supported = ", ".join(sorted(STAGE_SECTION_KEYS))
        raise HTTPException(status_code=400, detail=f"Unsupported stage. Supported stages: {supported}")

    output_dir = state.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=409, detail="Current stage output directory is not available.")

    if invalidate_downstream:
        state = _invalidate_downstream_state(state, stage)

    state[state_key] = content
    stage_files = dict(state.get("stage_files", {}))
    filename = FALLBACK_FILENAMES.get(file_key)
    if filename is not None:
        if file_key == "storyboard":
            from stages.storyboard_stage import write_storyboard_xlsx

            path = Path(output_dir) / filename
            write_storyboard_xlsx(content, path)
            saved_path = str(path.resolve())
        else:
            saved_path = orchestrator.storage.save_stage(output_dir, filename, content)
        stage_files[file_key] = saved_path
    state["stage_files"] = stage_files

    _update_job(
        job_id,
        result_state=state,
        project_id=state.get("project_id"),
        available_sections=_available_sections_from_state(state),
    )
    _persist_workflow_files(job_id)
    return state


def _is_job_cancelled(job_id: str) -> bool:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return True
        cancel_event = job.get("cancel_event")
        event_cancelled = bool(cancel_event.is_set()) if hasattr(cancel_event, "is_set") else False
        return event_cancelled or job.get("status") == "cancelled" or bool(job.get("cancel_requested"))


def _get_job(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        return dict(job)


def _update_job(job_id: str, **updates: Any) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return
        job.update(updates)
        job["updated_at"] = _now_iso()


def _make_llm_token_callback(job_id: str, public_stage: str):
    def callback(model_stage: str, output_key: str, token: str, meta: dict[str, Any] | None = None) -> None:
        if not token:
            return
        _emit_job_stream_event(
            job_id,
            "token",
            {
                "type": "token",
                "job_id": job_id,
                "stage": public_stage,
                "model_stage": model_stage,
                "output_key": output_key,
                "token": token,
                "meta": meta or {},
            },
        )

    return callback


def _emit_job_stream_event(job_id: str, event: str, payload: dict[str, Any]) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        queue = job.get("event_queue") if job else None
    if queue is None:
        return
    try:
        queue.put_nowait({"event": event, "payload": payload})
    except Full:
        return


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _job_status_response(job: dict[str, Any]) -> StoryJobStatusResponse:
    return StoryJobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        project_id=job.get("project_id"),
        error=job.get("error"),
        result_url=f"/api/story-jobs/{job['job_id']}/result",
        files=_available_file_urls(job),
        workflow_mode=job.get("workflow_mode", "auto"),
        current_stage=job.get("current_stage"),
        pending_confirmation=job.get("pending_confirmation"),
        confirmed_stages=job.get("confirmed_stages", []),
        revision_counts=job.get("revision_counts", {}),
        available_sections=job.get("available_sections", []),
        pass_score=int(job.get("pass_score") if job.get("pass_score") is not None else 85),
        max_critic_retries=int(
            job.get("max_critic_retries") if job.get("max_critic_retries") is not None else 3
        ),
        cancel_requested=bool(job.get("cancel_requested")),
        replaced_by_job_id=job.get("replaced_by_job_id"),
        critic_reports=list(job.get("critic_reports", [])),
    )


async def _story_job_event_stream(job_id: str, request: Request):
    last_event = ""
    terminal_statuses = {"succeeded", "failed", "cancelled"}

    while True:
        if await request.is_disconnected():
            break

        try:
            job = _get_job(job_id)
        except HTTPException as exc:
            yield _sse_event("error", {"detail": exc.detail, "status_code": exc.status_code})
            break

        payload = _stream_payload_for_job(job)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if encoded != last_event:
            yield _sse_event("job", payload)
            last_event = encoded

        if job["status"] in terminal_statuses:
            yield _sse_event("done", {"job_id": job_id, "status": job["status"]})
            break

        event_queue = job.get("event_queue")
        if event_queue is None:
            await asyncio.sleep(0.25)
            continue

        try:
            stream_item = await asyncio.to_thread(event_queue.get, True, 0.25)
        except Empty:
            continue

        yield _sse_event(stream_item.get("event", "message"), stream_item.get("payload", {}))


def _stream_payload_for_job(job: dict[str, Any]) -> dict[str, Any]:
    status = _model_to_payload(_job_status_response(job))
    state = dict(job.get("result_state") or {})
    payload: dict[str, Any] = {
        "type": "job_update",
        "job": status,
    }

    current_stage = job.get("current_stage")
    if current_stage and current_stage in STAGE_SECTION_KEYS:
        stage_output = _stage_stream_output(state, current_stage)
        if stage_output is not None:
            payload["current_stage_output"] = stage_output

    available_outputs: dict[str, Any] = {}
    for section in job.get("available_sections", []):
        if section in {"final_script", "storyboard"}:
            continue
        stage_output = _stage_stream_output(state, section)
        if stage_output is not None:
            available_outputs[section] = {
                "section": stage_output["section"],
                "parsed": stage_output["parsed"],
                "display_text": stage_output["display_text"],
            }
    if available_outputs:
        payload["available_outputs"] = available_outputs

    if job.get("current_stage") == "final_script":
        payload["script_segment_progress"] = state.get("script_segment_progress") or {}
        payload["script_segments"] = state.get("script_segments") or []

    return payload


def _stage_stream_output(state: dict[str, Any], section: str) -> dict[str, Any] | None:
    state_key = STAGE_SECTION_KEYS.get(section)
    if state_key is None:
        return None

    content = state.get(state_key) or ""
    if not content:
        return None

    parsed = parse_json_object(content)
    return {
        "section": section,
        "content": content,
        "display_text": _display_text_from_content(content, section, parsed),
        "parsed": parsed,
    }


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"


def _available_file_urls(job: dict[str, Any]) -> dict[str, str]:
    if job["status"] != "succeeded":
        return {}

    state = job.get("result_state") or {}
    stage_files = state.get("stage_files", {})
    urls = {}
    for file_key in stage_files:
        if file_key in FALLBACK_FILENAMES:
            urls[file_key] = f"/api/story-jobs/{job['job_id']}/files/{file_key}"
    return urls


def _interactive_stage_order(payload: dict[str, Any]) -> list[str]:
    if payload.get("include_storyboard", True):
        return list(INTERACTIVE_STAGE_ORDER)
    return [stage for stage in INTERACTIVE_STAGE_ORDER if stage != "storyboard"]


def _runner_stage_name(stage: str) -> str:
    return "final_script" if stage == "final_script" else stage


def _file_key_for_stage(stage: str) -> str:
    file_key = STAGE_FILE_KEYS.get(stage)
    if file_key is None:
        supported = ", ".join(sorted(STAGE_FILE_KEYS))
        raise HTTPException(status_code=400, detail=f"Unsupported stage. Supported stages: {supported}")
    return file_key


def _next_interactive_stage(stage: str, payload: dict[str, Any]) -> str | None:
    stage_order = _interactive_stage_order(payload)
    try:
        index = stage_order.index(stage)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported stage: {stage}") from None
    next_index = index + 1
    if next_index >= len(stage_order):
        return None
    return stage_order[next_index]


def _normalize_confirm_stages(value: Any) -> list[str]:
    if value is None:
        return list(DEFAULT_CONFIRM_STAGES)
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="confirm_stages must be a list of stage names.")

    normalized: list[str] = []
    unsupported: list[str] = []
    for item in value:
        stage = str(item).strip()
        if stage not in CONFIRMABLE_STAGES:
            unsupported.append(stage)
        elif stage not in normalized:
            normalized.append(stage)

    if unsupported:
        supported = ", ".join(sorted(CONFIRMABLE_STAGES))
        raise HTTPException(status_code=400, detail=f"Unsupported confirm_stages: {unsupported}. Supported: {supported}")
    return normalized


def _available_sections_from_state(state: dict[str, Any]) -> list[str]:
    sections: list[str] = []
    for section, state_key in STAGE_SECTION_KEYS.items():
        if state.get(state_key):
            sections.append(section)
    return sections


def _invalidate_downstream_state(state: dict[str, Any], stage: str) -> dict[str, Any]:
    stage_order = INTERACTIVE_STAGE_ORDER
    try:
        start_index = stage_order.index(stage)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported stage: {stage}") from None

    invalid_stages = stage_order[start_index + 1 :]
    invalid_keys = {STAGE_SECTION_KEYS.get(item, item) for item in invalid_stages}
    if "outline" in invalid_stages or stage == "outline":
        invalid_keys.add("outline_critic")
    updated = dict(state)
    for key in invalid_keys:
        updated.pop(key, None)
    if "outline_critic" in invalid_keys:
        updated.pop("critic_reports", None)

    stage_files = dict(updated.get("stage_files", {}))
    for key in invalid_keys:
        stage_path = stage_files.pop(key, None)
        _delete_stage_file(updated.get("output_dir"), key, stage_path)
    updated["stage_files"] = stage_files
    return updated


def _invalidate_stage_and_downstream_state(state: dict[str, Any], stage: str) -> dict[str, Any]:
    stage_order = INTERACTIVE_STAGE_ORDER
    try:
        start_index = stage_order.index(stage)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported stage: {stage}") from None

    updated = _invalidate_downstream_state(state, stage)
    keys = {STAGE_SECTION_KEYS.get(stage, stage)}
    if stage == "outline":
        keys.add("outline_critic")
        keys.add("critic_reports")
    if stage == "final_script":
        keys.update({"script_segments", "script_segment_progress"})

    for key in keys:
        updated.pop(key, None)

    stage_files = dict(updated.get("stage_files", {}))
    for key in keys:
        if key == "critic_reports":
            continue
        stage_path = stage_files.pop(key, None)
        _delete_stage_file(updated.get("output_dir"), key, stage_path)

    updated["stage_files"] = stage_files
    return updated


def _delete_stage_file(output_dir: str | None, file_key: str, stage_path: str | None = None) -> None:
    if not output_dir:
        return

    output_root = Path(output_dir).resolve()
    candidates: list[Path] = []
    if stage_path:
        candidates.append(Path(stage_path).resolve())
    fallback = FALLBACK_FILENAMES.get(file_key)
    if fallback:
        candidates.append((output_root / fallback).resolve())

    for path in candidates:
        try:
            path.relative_to(output_root)
        except ValueError:
            continue
        if path.exists() and path.is_file():
            path.unlink()


def _confirmed_without_downstream(confirmed_stages: list[str], stage: str) -> list[str]:
    try:
        start_index = INTERACTIVE_STAGE_ORDER.index(stage)
    except ValueError:
        return list(confirmed_stages)
    invalid = set(INTERACTIVE_STAGE_ORDER[start_index:])
    if "outline" in invalid:
        invalid.add("outline_critic")
    return [item for item in confirmed_stages if item not in invalid]


def _stage_invalidates_outline_critic(stage: str) -> bool:
    try:
        return INTERACTIVE_STAGE_ORDER.index(stage) <= INTERACTIVE_STAGE_ORDER.index("outline")
    except ValueError:
        return False


def _append_revision_history(
    job_id: str,
    stage: str,
    action: str,
    feedback: str,
    revision_mode: str | None = None,
) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return
        history = list(job.get("revision_history", []))
        history.append(
            {
                "stage": stage,
                "action": action,
                "feedback": feedback,
                "revision_mode": revision_mode,
                "created_at": _now_iso(),
            }
        )
        job["revision_history"] = history
        job["updated_at"] = _now_iso()
    _persist_workflow_files(job_id)


def _persist_workflow_files(job_id: str) -> None:
    job = _get_job(job_id)
    state = dict(job.get("result_state") or {})
    output_dir = state.get("output_dir")
    if not output_dir:
        return

    stage_files = dict(state.get("stage_files", {}))
    workflow_state = {
        "job_id": job["job_id"],
        "status": job["status"],
        "workflow_mode": job.get("workflow_mode", "auto"),
        "current_stage": job.get("current_stage"),
        "pending_confirmation": job.get("pending_confirmation"),
        "confirmed_stages": job.get("confirmed_stages", []),
        "revision_counts": job.get("revision_counts", {}),
        "available_sections": job.get("available_sections", []),
        "pass_score": int(job.get("pass_score") if job.get("pass_score") is not None else 85),
        "max_critic_retries": int(
            job.get("max_critic_retries") if job.get("max_critic_retries") is not None else 3
        ),
        "cancel_requested": bool(job.get("cancel_requested")),
        "replaced_by_job_id": job.get("replaced_by_job_id"),
        "critic_reports": job.get("critic_reports", []),
        "project_id": job.get("project_id") or state.get("project_id"),
        "updated_at": job.get("updated_at"),
    }

    workflow_path = Path(output_dir) / "workflow_state.json"
    revision_path = Path(output_dir) / "revision_history.json"
    workflow_path.write_text(json.dumps(workflow_state, ensure_ascii=False, indent=2), encoding="utf-8")
    revision_path.write_text(json.dumps(job.get("revision_history", []), ensure_ascii=False, indent=2), encoding="utf-8")
    stage_files["workflow_state"] = str(workflow_path.resolve())
    stage_files["revision_history"] = str(revision_path.resolve())
    state["stage_files"] = stage_files
    _update_job(job_id, result_state=state)


def _resolve_result_file(state: dict[str, Any], file_key: str) -> Path | None:
    stage_files = state.get("stage_files", {})
    stage_path = stage_files.get(file_key)
    if stage_path:
        path = Path(stage_path)
        if path.exists() and path.is_file():
            return path

    output_dir = state.get("output_dir")
    fallback_filename = FALLBACK_FILENAMES.get(file_key)
    if output_dir and fallback_filename:
        path = Path(output_dir) / fallback_filename
        if path.exists() and path.is_file():
            return path
    return None


def _resolve_project_file(project_id: str, file_key: str) -> Path | None:
    filename = FALLBACK_FILENAMES.get(file_key)
    if filename is None:
        return None

    output_root = orchestrator.settings.output_root.resolve()
    path = (output_root / project_id / filename).resolve()
    try:
        path.relative_to(output_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id")

    if path.exists() and path.is_file():
        return path
    return None


def _characters_response_from_state(
    state: dict[str, Any],
    *,
    job_id: str | None = None,
    project_id: str | None = None,
    status: JobStatus | None = None,
    file_url: str | None = None,
) -> CharactersResponse:
    characters = state.get("characters") or ""
    file_path = _resolve_result_file(state, "characters")

    if file_path is not None:
        if not characters:
            characters = file_path.read_text(encoding="utf-8")

    if not characters:
        raise HTTPException(status_code=404, detail="Characters content is not available.")

    parsed = parse_json_object(characters)
    return CharactersResponse(
        job_id=job_id,
        project_id=project_id,
        status=status,
        characters=characters,
        display_text=_display_text_from_content(characters, "characters", parsed),
        parsed=parsed,
        file_url=file_url,
    )


def _story_job_stage_section_response(job_id: str, section: str) -> StageSectionResponse:
    job = _get_job(job_id)
    if job["status"] != "succeeded":
        raise HTTPException(status_code=409, detail=f"Job is not completed yet: {job['status']}")

    state = job.get("result_state") or {}
    return _stage_section_response_from_state(
        state,
        section,
        job_id=job["job_id"],
        project_id=state.get("project_id") or job.get("project_id"),
        status=job["status"],
        file_url=f"/api/story-jobs/{job['job_id']}/files/{STAGE_FILE_KEYS[section]}",
    )


def _project_stage_section_response(project_id: str, section: str) -> StageSectionResponse:
    file_key = STAGE_FILE_KEYS[section]
    path = _resolve_project_file(project_id, file_key)
    if path is None:
        raise HTTPException(status_code=404, detail=f"{section} file not found for project: {project_id}")

    content = path.read_text(encoding="utf-8")
    return _build_stage_section_response(
        section=section,
        content=content,
        project_id=project_id,
        file_url=f"/api/projects/{project_id}/{section}",
    )


def _stage_section_response_from_state(
    state: dict[str, Any],
    section: str,
    *,
    job_id: str | None = None,
    project_id: str | None = None,
    status: JobStatus | None = None,
    file_url: str | None = None,
) -> StageSectionResponse:
    state_key = STAGE_SECTION_KEYS[section]
    file_key = STAGE_FILE_KEYS[section]
    content = state.get(state_key) or ""
    file_path = _resolve_result_file(state, file_key)

    if file_path is not None and not content:
        content = file_path.read_text(encoding="utf-8")

    if not content:
        raise HTTPException(status_code=404, detail=f"{section} content is not available.")

    return _build_stage_section_response(
        section=section,
        content=content,
        job_id=job_id,
        project_id=project_id,
        status=status,
        file_url=file_url,
    )


def _stage_content_response_from_state(
    state: dict[str, Any],
    section: str,
    *,
    job_id: str | None = None,
    project_id: str | None = None,
    status: JobStatus | None = None,
    file_url: str | None = None,
) -> StageContentResponse:
    if section not in STAGE_SECTION_KEYS:
        supported = ", ".join(sorted(STAGE_SECTION_KEYS))
        raise HTTPException(status_code=400, detail=f"Unsupported stage. Supported stages: {supported}")

    state_key = STAGE_SECTION_KEYS[section]
    file_key = STAGE_FILE_KEYS[section]
    content = state.get(state_key) or ""
    file_path = _resolve_result_file(state, file_key)
    if file_path is not None and not content:
        content = file_path.read_text(encoding="utf-8")

    if not content:
        raise HTTPException(status_code=404, detail=f"{section} content is not available.")

    return _build_stage_content_response(
        section=section,
        content=content,
        job_id=job_id,
        project_id=project_id,
        status=status,
        file_url=file_url,
    )


def _build_stage_content_response(
    *,
    section: str,
    content: str,
    job_id: str | None = None,
    project_id: str | None = None,
    status: JobStatus | None = None,
    file_url: str | None = None,
) -> StageContentResponse:
    parsed = parse_json_object(content)
    return StageContentResponse(
        job_id=job_id,
        project_id=project_id,
        status=status,
        section=section,
        content=content,
        display_text=_display_text_from_content(content, section, parsed),
        parsed=parsed,
        file_url=file_url,
    )


def _build_stage_section_response(
    *,
    section: str,
    content: str,
    job_id: str | None = None,
    project_id: str | None = None,
    status: JobStatus | None = None,
    file_url: str | None = None,
) -> StageSectionResponse:
    parsed = parse_json_object(content)
    values: dict[str, Any] = {
        "job_id": job_id,
        "project_id": project_id,
        "status": status,
        "section": section,
        "content": content,
        "display_text": _display_text_from_content(content, section, parsed),
        "parsed": parsed,
        "file_url": file_url,
    }
    values[section] = content
    return StageSectionResponse(**values)


def _display_text_from_content(content: str, section: str, parsed: Any = None) -> str:
    data = parsed if parsed is not None else parse_json_object(content)
    if data is None:
        return content.strip()

    if section == "characters":
        return _format_characters_display(data)
    if section == "world":
        return _format_world_display(data)
    if section == "relationships":
        return _format_relationships_display(data)
    if section == "relationship_graph":
        return _format_relationship_graph_display(data)
    if section == "biography":
        return _format_biography_display(data)
    if section == "outline":
        return _format_outline_display(data)
    if section == "outline_critic":
        return _format_outline_critic_display(data)
    if section in {"logline", "final_script"}:
        return content.strip()
    return _format_display_value(data)


def _format_world_display(data: Any) -> str:
    world = _unwrap_section(data, "world")
    if not isinstance(world, dict):
        return _format_display_value(data)

    lines = ["# 世界观设定"]
    for key, value in world.items():
        lines.extend(["", f"## {_display_label(key)}"])
        lines.extend(_format_value_lines(value))
    return "\n".join(lines).strip()


def _format_characters_display(data: Any) -> str:
    characters = _unwrap_section(data, "characters")
    if not isinstance(characters, dict):
        return _format_display_value(data)

    lines = ["# 角色设置"]
    for role_key, value in characters.items():
        lines.extend(["", f"## {_display_label(role_key)}"])
        lines.extend(_format_value_lines(value))
    return "\n".join(lines).strip()


def _format_relationships_display(data: Any) -> str:
    relationships = _unwrap_section(data, "relationships")
    if not isinstance(relationships, list):
        return _format_display_value(data)

    lines = ["# 人物关系"]
    for index, item in enumerate(relationships, start=1):
        if isinstance(item, dict):
            title = item.get("name") or f"关系 {index}"
            lines.extend(["", f"## {index}. {title}"])
            lines.extend(_format_mapping_lines(item, skip_keys={"name"}))
        else:
            lines.extend(["", f"## {index}. 关系", str(item)])
    return "\n".join(lines).strip()


def _format_relationship_graph_display(data: Any) -> str:
    graph = _unwrap_section(data, "relationship_graph")
    if not isinstance(graph, list):
        return _format_display_value(data)

    lines = ["# 人物关系图"]
    for index, item in enumerate(graph, start=1):
        if isinstance(item, dict):
            source = item.get("source") or "A"
            target = item.get("target") or "B"
            relationship = item.get("relationship") or ""
            lines.append(f"{index}. {source} - {target}：{relationship}")
        else:
            lines.append(f"{index}. {item}")
    return "\n".join(lines).strip()


def _format_biography_display(data: Any) -> str:
    if not isinstance(data, dict):
        return _format_display_value(data)

    lines = ["# 人物小传"]
    if data.get("protagonist_biography"):
        lines.extend(["", "## 主角小传", str(data["protagonist_biography"])])

    for key in ("core_supporting_biographies", "functional_supporting_biographies"):
        values = data.get(key)
        if values is None:
            continue
        lines.extend(["", f"## {_display_label(key)}"])
        lines.extend(_format_value_lines(values))

    handled = {"protagonist_biography", "core_supporting_biographies", "functional_supporting_biographies"}
    for key, value in data.items():
        if key not in handled:
            lines.extend(["", f"## {_display_label(key)}"])
            lines.extend(_format_value_lines(value))

    return "\n".join(lines).strip()


def _format_outline_critic_display(data: Any) -> str:
    reports = data.get("critic_reports") if isinstance(data, dict) else None
    if not isinstance(reports, list):
        reports = [data] if isinstance(data, dict) else []
    if not reports:
        return _format_display_value(data)

    lines = ["# 评论家报告"]
    for index, report in enumerate(reports, start=1):
        if not isinstance(report, dict):
            lines.extend(["", f"## 第 {index} 次", str(report)])
            continue
        lines.extend(["", f"## 第 {index} 次"])
        lines.extend(_format_mapping_lines(report))
    return "\n".join(lines).strip()


def _format_outline_display(data: Any) -> str:
    if not isinstance(data, dict):
        return _format_display_value(data)

    lines = ["# 故事大纲"]
    if data.get("duration_minutes") is not None:
        lines.extend(["", f"影片时长：{data['duration_minutes']} 分钟"])

    three_act = data.get("three_act_outline")
    if isinstance(three_act, dict):
        lines.extend(["", "## 三幕式大纲"])
        for key, value in three_act.items():
            lines.extend(["", f"### {_display_label(key)}"])
            lines.extend(_format_value_lines(value))

    chapters = data.get("chapter_outline")
    if isinstance(chapters, list):
        lines.extend(["", "## 章节细纲"])
        for index, chapter in enumerate(chapters, start=1):
            if isinstance(chapter, dict):
                title = chapter.get("chapter") or f"章节 {index}"
                lines.extend(["", f"### {index}. {title}"])
                lines.extend(_format_mapping_lines(chapter, skip_keys={"chapter"}))
            else:
                lines.extend(["", f"### {index}. 章节", str(chapter)])

    handled = {"duration_minutes", "three_act_outline", "chapter_outline"}
    for key, value in data.items():
        if key not in handled:
            lines.extend(["", f"## {_display_label(key)}"])
            lines.extend(_format_value_lines(value))

    return "\n".join(lines).strip()


def _format_display_value(value: Any) -> str:
    return "\n".join(_format_value_lines(value)).strip()


def _format_value_lines(value: Any) -> list[str]:
    if isinstance(value, dict):
        return _format_mapping_lines(value)
    if isinstance(value, list):
        lines: list[str] = []
        for index, item in enumerate(value, start=1):
            if isinstance(item, dict):
                title = item.get("name") or item.get("chapter") or f"第 {index} 项"
                lines.append(f"{index}. {title}")
                lines.extend(f"   {line}" for line in _format_mapping_lines(item, skip_keys={"name", "chapter"}))
            else:
                lines.append(f"{index}. {item}")
        return lines
    return [str(value)]


def _format_mapping_lines(mapping: dict[str, Any], skip_keys: set[str] | None = None) -> list[str]:
    skip_keys = skip_keys or set()
    lines: list[str] = []
    for key, value in mapping.items():
        if key in skip_keys:
            continue
        label = _display_label(key)
        if isinstance(value, (dict, list)):
            lines.append(f"{label}：")
            lines.extend(f"  {line}" for line in _format_value_lines(value))
        else:
            lines.append(f"{label}：{value}")
    return lines


def _unwrap_section(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data:
        return data[key]
    return data


def _display_label(key: Any) -> str:
    return DISPLAY_LABELS.get(str(key), str(key))


def _media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix == ".json":
        return "application/json"
    if suffix in {".md", ".txt"}:
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def _model_to_payload(model: BaseModel) -> dict[str, Any]:
    try:
        return model.model_dump()
    except AttributeError:  # pydantic v1 fallback
        return model.dict()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
