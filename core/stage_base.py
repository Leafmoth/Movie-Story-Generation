from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from core.llm_client import ChatMessage, LLMClient
from core.state import ProjectState
from core.storage import ProjectStorage, parse_json_object


PostProcess = Callable[[ProjectState, str], dict[str, str]]


@dataclass
class PromptStage:
    name: str
    prompt_file: str
    output_key: str
    output_filename: str
    prompt_dir: Path
    llm: LLMClient
    storage: ProjectStorage
    placeholders: Mapping[str, str] = field(default_factory=dict)
    postprocess: PostProcess | None = None
    system_prompt: str = "你是一位从业十余年的资深电影编剧。严格遵守用户给定提示词，不改变原意。"

    def run(self, state: ProjectState) -> ProjectState:
        prompt = self._render_prompt(state)
        messages = [
            ChatMessage(
                role="system",
                content=self.system_prompt,
            ),
            ChatMessage(role="user", content=prompt),
        ]
        token_callback = state.get("llm_token_callback")
        if callable(token_callback):
            content = self.llm.generate_stream(
                messages,
                stage_name=self.name,
                on_token=lambda token: token_callback(self.name, self.output_key, token, {}),
            )
        else:
            content = self.llm.generate(messages, stage_name=self.name)
        saved_path = self.save_content(state, content)

        stage_files = dict(state.get("stage_files", {}))
        stage_files[self.output_key] = saved_path

        updates: ProjectState = {
            self.output_key: content,
            "stage_files": stage_files,
        }
        if self.postprocess is not None:
            updates.update(self.postprocess(state, content))
        return updates

    def save_content(self, state: ProjectState, content: str) -> str:
        return self.storage.save_stage(state["output_dir"], self.output_filename, content)

    def _render_prompt(self, state: ProjectState) -> str:
        template = (self.prompt_dir / self.prompt_file).read_text(encoding="utf-8")
        values = dict(state)
        values.setdefault("theme_question", "未填写，请结合一句话概括自动完善。")
        values.setdefault("genre", "未填写，请自动补充。")

        for placeholder, state_key in self.placeholders.items():
            values[placeholder] = values.get(state_key, "")

        for key, value in values.items():
            template = template.replace(f"[[{key}]]", str(value or ""))

        world_context = str(state.get("world") or "").strip()
        if world_context and self.output_key in {"characters", "outline"}:
            template = (
                f"{template}\n\n"
                "世界观设定，请后续创作严格遵守：\n"
                f"{world_context}\n"
            )

        revision_feedback = str(state.get("revision_feedback") or "").strip()
        if revision_feedback:
            revision_mode = str(state.get("revision_mode") or "modify").strip()
            previous_content = str(state.get(self.output_key) or "").strip()
            if self.output_key == "logline" and revision_mode == "rewrite":
                template = (
                    f"{template}\n\n"
                    "用户否认了上一版故事梗概，并选择重写。请只基于下面这版用户重写内容重新生成本阶段输出：\n"
                    f"{revision_feedback}\n"
                )
            else:
                template = (
                    f"{template}\n"
                    "用户对本阶段的修改反馈：\n"
                    f"{revision_feedback}\n"
                )
                if previous_content:
                    template = (
                        f"{template}\n"
                        "本阶段上一版输出如下，请结合用户反馈，在保留可用内容的基础上修改：\n"
                        f"{previous_content}\n"
                    )
        return template


def logline_postprocess(state: ProjectState, content: str) -> dict[str, str]:
    parsed = parse_json_object(content)
    if not isinstance(parsed, dict):
        return {}

    updates: dict[str, str] = {}
    genre = _pick(parsed, "genre", "影片类型", "type")
    if genre and not state.get("genre"):
        updates["genre"] = genre
    return updates


def _pick(data: dict, *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
