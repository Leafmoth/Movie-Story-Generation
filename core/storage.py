from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4


class ProjectStorage:
    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

    def new_project_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"project_{timestamp}_{uuid4().hex[:8]}"

    def create_project_dir(self, project_id: str) -> Path:
        clean_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", project_id).strip("._") or self.new_project_id()
        project_dir = self.output_root / clean_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    def save_stage(self, output_dir: str | Path, filename: str, content: str) -> str:
        path = Path(output_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.suffix.lower() == ".json":
            parsed = parse_json_object(content)
            data = parsed if parsed is not None else {"content": content}
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text(content, encoding="utf-8")

        return str(path.resolve())


def parse_json_object(text: str) -> dict | list | None:
    stripped = text.strip()
    if not stripped:
        return None

    for candidate in _json_candidates(stripped):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed
    return None


def _json_candidates(text: str) -> list[str]:
    candidates = [text]
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            candidates.append("\n".join(lines[1:-1]))

    object_start = text.find("{")
    object_end = text.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(text[object_start : object_end + 1])

    array_start = text.find("[")
    array_end = text.rfind("]")
    if array_start >= 0 and array_end > array_start:
        candidates.append(text[array_start : array_end + 1])

    return candidates
