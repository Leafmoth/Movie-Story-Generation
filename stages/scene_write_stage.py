from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.json_utils import parse_json_result
from core.llm_client import ChatMessage, LLMClient
from core.stage_base import PromptStage
from core.state import ProjectState
from core.storage import parse_json_object
from core.storage import ProjectStorage


SCENE_CONTEXT_LIMIT = 1800
SCENE_PREVIOUS_LIMIT = 1600
SCENE_BATCH_RETRIES = 2


class ChunkedSceneWriteStage(PromptStage):
    def run(self, state: ProjectState) -> ProjectState:
        outline_items = _outline_items(state.get("outline") or "")
        segments: list[dict[str, Any]] = []
        progress_callback = state.get("script_segment_callback")
        token_callback = state.get("llm_token_callback")

        for index, item in enumerate(outline_items, start=1):
            last_error = ""
            parsed: dict[str, Any] | None = None
            for attempt in range(1, SCENE_BATCH_RETRIES + 1):
                prompt = _scene_prompt(state, item, index, segments[-3:], last_error)
                messages = [
                    ChatMessage(
                        role="system",
                        content="你是资深电影编剧。只输出合法 JSON，不输出 Markdown 或解释。",
                    ),
                    ChatMessage(role="user", content=prompt),
                ]
                if callable(token_callback):
                    raw = self.llm.generate_stream(
                        messages,
                        stage_name="scene_write_chunk",
                        on_token=lambda token, segment_index=index: token_callback(
                            "scene_write_chunk",
                            self.output_key,
                            token,
                            {
                                "segment_index": segment_index,
                                "segment_total": len(outline_items),
                            },
                        ),
                    )
                else:
                    raw = self.llm.generate(messages, stage_name="scene_write_chunk")
                candidate = parse_json_result(raw, expected_type="dict")
                if not isinstance(candidate, dict):
                    last_error = f"没有返回合法 JSON，疑似被截断。模型输出片段：{raw[:500]}"
                    continue

                script_text = str(candidate.get("script_text") or "").strip()
                if not script_text:
                    last_error = "缺少 script_text，无法保存当前剧本片段。"
                    continue

                candidate.setdefault("scene", item.get("chapter") or f"第{index}场")
                candidate.setdefault("title", item.get("chapter") or f"第{index}场")
                candidate.setdefault("act", item.get("act") or "")
                candidate.setdefault("estimated_duration_minutes", item.get("duration_minutes") or "")
                critic = _critic_scene(self.llm, state, item, candidate, segments[-3:])
                candidate["scene_critic"] = critic
                if critic.get("passed"):
                    parsed = candidate
                    break
                last_error = str(critic.get("revision_advice") or "当前片段未通过连续性、时长或人物逻辑检查，请重写。")

            if parsed is None:
                raise ValueError(f"第 {index} 个剧本片段生成失败，已重试但仍未通过。最后问题：{last_error}")
            segments.append(parsed)
            if callable(progress_callback):
                progress_callback(index, len(outline_items), list(segments), _assemble_script(segments))

        content = _assemble_script(segments)
        saved_path = self.save_content(state, content)
        stage_files = dict(state.get("stage_files", {}))
        stage_files[self.output_key] = saved_path
        return {
            self.output_key: content,
            "script_segments": segments,
            "stage_files": stage_files,
        }


def make_scene_write_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return ChunkedSceneWriteStage(
        name="scene_write",
        prompt_file="scene_write_prompt.txt",
        output_key="final_script",
        output_filename="final_script.md",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={"outline": "outline", "duration_minutes": "duration_minutes"},
    )


def _outline_items(outline_text: str) -> list[dict[str, Any]]:
    parsed = parse_json_object(outline_text)
    if isinstance(parsed, dict):
        chapters = parsed.get("chapter_outline") or parsed.get("chapters")
        if isinstance(chapters, list) and chapters:
            return [chapter if isinstance(chapter, dict) else {"summary": str(chapter)} for chapter in chapters]
    return [{"chapter": "完整剧本", "summary": outline_text, "duration_minutes": ""}]


def _scene_prompt(
    state: ProjectState,
    outline_item: dict[str, Any],
    scene_index: int,
    previous_segments: list[dict[str, Any]],
    last_error: str = "",
) -> str:
    previous_summary = [
        {
            "scene": item.get("scene"),
            "title": item.get("title"),
            "continuity_notes": item.get("continuity_notes"),
            "tail": str(item.get("script_text") or "")[-500:],
        }
        for item in previous_segments
    ]
    context = {
        "用户最初输入": state.get("input_logline"),
        "故事梗概": state.get("logline"),
        "世界观": state.get("world"),
        "角色设置": state.get("characters"),
        "人物关系": state.get("character_relations"),
        "人物关系图": state.get("relationship_graph"),
        "类型": state.get("genre"),
        "主题问题": state.get("theme_question"),
        "目标片长": state.get("duration_minutes"),
    }
    feedback = f"\n上一次生成未通过，原因：{last_error}\n请只重写当前片段并修正问题。" if last_error else ""
    return f"""
请只生成当前这一场/这一章的文学剧本片段，不要续写其他章节。

全局上下文：
{_compact_json(context, SCENE_CONTEXT_LIMIT)}

当前大纲节点：
{_compact_json(outline_item, SCENE_CONTEXT_LIMIT)}

最近已完成片段摘要：
{_compact_json(previous_summary, SCENE_PREVIOUS_LIMIT)}
{feedback}

输出要求：
1. 只输出一个合法 JSON object。
2. script_text 写文学剧本正文，必须包含场景编号、场景描述、动作和对白。
3. 继承当前大纲节点的 duration_minutes；每场戏标注“本场预计时长”。
4. continuity_notes 记录本场结束后的事实、情绪、人物状态和未解决问题，供下一场接续。
5. constraint_check 用数组列出本场如何满足时长、人物关系、世界观和连续性。

JSON 结构：
{{
  "act": "{outline_item.get('act', '')}",
  "scene": "{scene_index}",
  "title": "{outline_item.get('chapter') or outline_item.get('title') or '当前场'}",
  "estimated_duration_minutes": "{outline_item.get('duration_minutes', '')}",
  "script_text": "...",
  "continuity_notes": "...",
  "constraint_check": ["..."]
}}
""".strip()


def _critic_scene(
    llm: LLMClient,
    state: ProjectState,
    outline_item: dict[str, Any],
    segment: dict[str, Any],
    previous_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = f"""
请检查当前剧本片段是否可以进入下一场。只输出 JSON object。

检查维度：
1. 是否覆盖当前大纲节点。
2. 是否符合世界观、角色设置和人物关系。
3. 是否接住最近已完成片段的事实、情绪和人物状态。
4. 是否包含可拍的动作和有效对白。
5. 是否标注并遵守当前节点的预计时长。

当前大纲节点：
{_compact_json(outline_item, SCENE_CONTEXT_LIMIT)}

最近片段摘要：
{_compact_json(previous_segments, SCENE_PREVIOUS_LIMIT)}

当前剧本片段：
{_compact_json(segment, SCENE_CONTEXT_LIMIT)}

JSON 结构：
{{
  "passed": true,
  "issues": [],
  "revision_advice": ""
}}
""".strip()
    raw = llm.generate(
        [
            ChatMessage(role="system", content="你是剧本连续性评论家。只输出合法 JSON。"),
            ChatMessage(role="user", content=prompt),
        ],
        stage_name="scene_write_critic",
    )
    parsed = parse_json_result(raw, expected_type="dict")
    if not isinstance(parsed, dict):
        return {
            "passed": False,
            "issues": ["评论家没有返回合法 JSON。"],
            "revision_advice": "请重写当前片段，并确保结构、人物动机、时长和连续性清晰。",
        }
    issues = parsed.get("issues")
    if not isinstance(issues, list):
        issues = [str(issues)] if issues else []
    return {
        "passed": bool(parsed.get("passed")) and not issues,
        "issues": issues,
        "revision_advice": str(parsed.get("revision_advice") or "").strip(),
    }


def _assemble_script(segments: list[dict[str, Any]]) -> str:
    lines = ["# 文学剧本"]
    for index, segment in enumerate(segments, start=1):
        title = str(segment.get("title") or segment.get("scene") or f"第{index}场").strip()
        duration = str(segment.get("estimated_duration_minutes") or "").strip()
        lines.extend(["", f"## {index}. {title}"])
        if duration:
            lines.append(f"预计时长：{duration}分钟")
        lines.extend(["", str(segment.get("script_text") or "").strip()])
        notes = str(segment.get("continuity_notes") or "").strip()
        if notes:
            lines.extend(["", f"连续性备注：{notes}"])
    return "\n".join(lines).strip() + "\n"


def _compact_json(value: Any, limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...（已压缩）"
