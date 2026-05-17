from __future__ import annotations

from pathlib import Path
import json

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.state import ProjectState
from core.storage import ProjectStorage, parse_json_object


ROLE_KEYS = ("protagonist", "antagonist", "emotional_core", "ally", "mirror")
PHYSIOLOGICAL_FIELDS = ("姓名", "身高", "体重", "年龄", "外貌")
PSYCHOLOGICAL_FIELDS = ("感情生活", "道德标准", "情商智商")
INTERNAL_FIELDS = ("人物创伤", "人物缺陷", "人物性格", "人物选择", "人物动机")
SOCIAL_OPTIONAL_FIELDS = {"社会阶层", "职业", "教育程度", "家庭", "宗教信仰"}
INTERNAL_OPTIONAL_FIELDS = {"人物相信的谎言", "人物欲望", "人物弧光"}


def make_character_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return PromptStage(
        name="characters",
        prompt_file="character_prompt.txt",
        output_key="characters",
        output_filename="02_characters.json",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={"Logline": "logline", "world": "world"},
        postprocess=lambda state, content: _character_postprocess(state, content, storage),
    )


def _character_postprocess(state: ProjectState, content: str, storage: ProjectStorage) -> dict[str, object]:
    parsed = parse_json_object(content)
    if not isinstance(parsed, dict):
        return {}

    normalized = _normalize_characters(parsed, list(state.get("character_detail_fields") or []))
    normalized_content = json.dumps(normalized, ensure_ascii=False, indent=2)
    saved_path = storage.save_stage(state["output_dir"], "02_characters.json", normalized_content)
    stage_files = dict(state.get("stage_files", {}))
    stage_files["characters"] = saved_path
    return {
        "characters": normalized_content,
        "stage_files": stage_files,
    }


def _normalize_characters(data: dict, selected_fields: list[str]) -> dict:
    characters = data.get("characters")
    if not isinstance(characters, dict):
        return data

    normalized_characters = dict(characters)
    selected = {str(field).strip() for field in selected_fields if str(field).strip()}
    for role_key in ROLE_KEYS:
        role_value = normalized_characters.get(role_key)
        normalized_characters[role_key] = _normalize_character_role(role_value, selected)

    result = dict(data)
    result["characters"] = normalized_characters
    return result


def _normalize_character_role(value: object, selected_fields: set[str]) -> dict:
    role = value if isinstance(value, dict) else {}
    external = role.get("external") if isinstance(role.get("external"), dict) else {}
    physiological = external.get("physiological") if isinstance(external.get("physiological"), dict) else {}
    psychological = external.get("psychological") if isinstance(external.get("psychological"), dict) else {}
    social = external.get("social") if isinstance(external.get("social"), dict) else {}
    internal = role.get("internal") if isinstance(role.get("internal"), dict) else {}

    normalized = dict(role)
    normalized["external"] = {
        "physiological": _with_required_keys(physiological, PHYSIOLOGICAL_FIELDS),
        "psychological": _with_required_keys(psychological, PSYCHOLOGICAL_FIELDS),
        "social": _with_required_keys(social, [field for field in selected_fields if field in SOCIAL_OPTIONAL_FIELDS]),
    }
    normalized["internal"] = _with_required_keys(
        internal,
        [*INTERNAL_FIELDS, *[field for field in selected_fields if field in INTERNAL_OPTIONAL_FIELDS]],
    )
    return normalized


def _with_required_keys(source: dict, keys: object) -> dict:
    normalized = dict(source)
    for key in keys:
        normalized.setdefault(str(key), "")
    return normalized
