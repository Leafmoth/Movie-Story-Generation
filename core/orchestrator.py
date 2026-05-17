from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Mapping

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
except Exception:  # pragma: no cover - dependency may not be installed yet
    LangChainPendingDeprecationWarning = Warning

warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects` will change.*",
    category=LangChainPendingDeprecationWarning,
)

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover - depends on local env
    END = START = StateGraph = None
    LANGGRAPH_IMPORT_ERROR = exc
else:
    LANGGRAPH_IMPORT_ERROR = None

from config.settings import Settings, get_settings
from core.llm_client import LLMClient
from core.state import ProjectState
from core.storage import ProjectStorage
from stages.biography_stage import make_biography_stage
from stages.character_stage import make_character_stage
from stages.critic_stage import make_outline_critic_stage
from stages.logline_stage import make_logline_stage
from stages.outline_stage import make_outline_stage
from stages.relationship_graph_stage import make_relationship_graph_stage
from stages.relationship_stage import make_relationship_stage
from stages.scene_write_stage import make_scene_write_stage
from stages.storyboard_stage import make_storyboard_stage
from stages.world_stage import make_world_stage


class StoryOrchestrator:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.storage = ProjectStorage(self.settings.output_root)
        self.llm = LLMClient(self.settings)
        self.stage_kwargs = {
            "prompt_dir": self.settings.prompt_dir,
            "llm": self.llm,
            "storage": self.storage,
        }
        self.storyboard_stage = make_storyboard_stage(**self.stage_kwargs)
        self.stages = self._make_stages()
        self.graph = self._build_graph()

    def generate(self, data: Mapping[str, Any], *, include_storyboard: bool = True) -> ProjectState:
        initial_state = self.create_initial_state(data, include_storyboard=include_storyboard)
        return self.graph.invoke(initial_state)

    def create_initial_state(self, data: Mapping[str, Any], *, include_storyboard: bool = True) -> ProjectState:
        project_id = str(data.get("project_id") or self.storage.new_project_id())
        output_dir = self.storage.create_project_dir(project_id)

        return {
            "project_id": project_id,
            "output_dir": str(output_dir.resolve()),
            "input_logline": str(data["logline"]).strip(),
            "theme_question": str(data.get("theme_question") or "").strip(),
            "duration_minutes": int(data["duration_minutes"]),
            "genre": str(data.get("genre") or "").strip(),
            "character_detail_fields": list(data.get("character_detail_fields") or []),
            "include_storyboard": include_storyboard,
            "stage_files": {},
            "metadata": {
                "model": self.settings.model_name,
                "pass_score": int(data.get("pass_score") if data.get("pass_score") is not None else 85),
                "max_critic_retries": int(
                    data.get("max_critic_retries") if data.get("max_critic_retries") is not None else 3
                ),
            },
        }

    def run_stage(
        self,
        state: ProjectState,
        stage_name: str,
        *,
        feedback: str = "",
        revision_mode: str = "modify",
    ) -> ProjectState:
        stage = self.stages.get(stage_name)
        if stage is None:
            supported = ", ".join(sorted(self.stages))
            raise ValueError(f"Unsupported stage: {stage_name}. Supported stages: {supported}")

        stage_state: ProjectState = dict(state)
        if feedback.strip():
            stage_state["revision_feedback"] = feedback.strip()
            stage_state["revision_mode"] = revision_mode
            if stage_name == "logline" and revision_mode == "rewrite":
                stage_state["input_logline"] = feedback.strip()
                stage_state.pop("logline", None)
        else:
            stage_state.pop("revision_feedback", None)
            stage_state.pop("revision_mode", None)

        updates = stage.run(stage_state)
        updated_state: ProjectState = dict(state)
        updated_state.update(updates)
        updated_state.pop("revision_feedback", None)
        updated_state.pop("revision_mode", None)
        return updated_state

    def generate_storyboard_from_script(
        self,
        *,
        final_script: str,
        project_id: str | None = None,
        output_dir: str | None = None,
        final_script_path: str | None = None,
    ) -> ProjectState:
        if output_dir:
            project_dir = Path(output_dir).resolve()
            project_dir.mkdir(parents=True, exist_ok=True)
        elif final_script_path:
            project_dir = Path(final_script_path).resolve().parent
            project_dir.mkdir(parents=True, exist_ok=True)
        else:
            project_dir = self.storage.create_project_dir(project_id or self.storage.new_project_id())

        state: ProjectState = {
            "project_id": project_id or project_dir.name,
            "output_dir": str(project_dir.resolve()),
            "final_script": final_script,
            "stage_files": {},
            "metadata": {"model": self.settings.model_name, "source": "storyboard_from_script"},
        }
        if final_script_path:
            state["stage_files"] = {"final_script": final_script_path}

        updates = self.storyboard_stage.run(state)
        state.update(updates)
        return state

    def _build_graph(self):
        if StateGraph is None:
            raise RuntimeError("Package 'langgraph' is missing. Run: pip install -r requirements.txt") from LANGGRAPH_IMPORT_ERROR

        graph = StateGraph(ProjectState)
        for node_name in (
            "logline",
            "world",
            "characters",
            "relationships",
            "relationship_graph",
            "biography",
            "outline",
            "outline_critic",
            "scene_write",
            "storyboard",
        ):
            graph.add_node(node_name, self.stages[node_name].run)

        graph.add_edge(START, "logline")
        graph.add_edge("logline", "world")
        graph.add_edge("world", "characters")
        graph.add_edge("characters", "relationships")
        graph.add_edge("relationships", "relationship_graph")
        graph.add_edge("relationship_graph", "biography")
        graph.add_edge("biography", "outline")
        graph.add_edge("outline", "outline_critic")
        graph.add_edge("outline_critic", "scene_write")
        graph.add_conditional_edges("scene_write", _route_after_scene_write)
        graph.add_edge("storyboard", END)
        return graph.compile()

    def _make_stages(self):
        return {
            "logline": make_logline_stage(**self.stage_kwargs),
            "world": make_world_stage(**self.stage_kwargs),
            "characters": make_character_stage(**self.stage_kwargs),
            "relationships": make_relationship_stage(**self.stage_kwargs),
            "relationship_graph": make_relationship_graph_stage(**self.stage_kwargs),
            "biography": make_biography_stage(**self.stage_kwargs),
            "outline": make_outline_stage(**self.stage_kwargs),
            "outline_critic": make_outline_critic_stage(**self.stage_kwargs),
            "scene_write": make_scene_write_stage(**self.stage_kwargs),
            "final_script": make_scene_write_stage(**self.stage_kwargs),
            "storyboard": self.storyboard_stage,
        }


def _route_after_scene_write(state: ProjectState) -> str:
    if state.get("include_storyboard", True):
        return "storyboard"
    return END
