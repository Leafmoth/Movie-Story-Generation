from __future__ import annotations

import warnings
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
from stages.logline_stage import make_logline_stage
from stages.outline_stage import make_outline_stage
from stages.relationship_stage import make_relationship_stage
from stages.scene_write_stage import make_scene_write_stage


class StoryOrchestrator:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.storage = ProjectStorage(self.settings.output_root)
        self.llm = LLMClient(self.settings)
        self.graph = self._build_graph()

    def generate(self, data: Mapping[str, Any]) -> ProjectState:
        project_id = str(data.get("project_id") or self.storage.new_project_id())
        output_dir = self.storage.create_project_dir(project_id)

        initial_state: ProjectState = {
            "project_id": project_id,
            "output_dir": str(output_dir.resolve()),
            "input_logline": str(data["logline"]).strip(),
            "theme_question": str(data.get("theme_question") or "").strip(),
            "duration_minutes": int(data["duration_minutes"]),
            "genre": str(data.get("genre") or "").strip(),
            "stage_files": {},
            "metadata": {"model": self.settings.model_name},
        }

        return self.graph.invoke(initial_state)

    def _build_graph(self):
        if StateGraph is None:
            raise RuntimeError("Package 'langgraph' is missing. Run: pip install -r requirements.txt") from LANGGRAPH_IMPORT_ERROR

        stage_kwargs = {
            "prompt_dir": self.settings.prompt_dir,
            "llm": self.llm,
            "storage": self.storage,
        }
        stages = {
            "logline": make_logline_stage(**stage_kwargs),
            "characters": make_character_stage(**stage_kwargs),
            "relationships": make_relationship_stage(**stage_kwargs),
            "biography": make_biography_stage(**stage_kwargs),
            "outline": make_outline_stage(**stage_kwargs),
            "scene_write": make_scene_write_stage(**stage_kwargs),
        }

        graph = StateGraph(ProjectState)
        for node_name, stage in stages.items():
            graph.add_node(node_name, stage.run)

        graph.add_edge(START, "logline")
        graph.add_edge("logline", "characters")
        graph.add_edge("characters", "relationships")
        graph.add_edge("relationships", "biography")
        graph.add_edge("biography", "outline")
        graph.add_edge("outline", "scene_write")
        graph.add_edge("scene_write", END)
        return graph.compile()
