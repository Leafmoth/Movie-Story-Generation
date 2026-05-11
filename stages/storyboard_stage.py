from __future__ import annotations

import csv
import io
from pathlib import Path

from core.llm_client import LLMClient
from core.stage_base import PromptStage
from core.state import ProjectState
from core.storage import ProjectStorage


HEADERS = [
    "#",
    "场次-镜号",
    "画面核心内容",
    "光学参数",
    "景别",
    "运镜调度",
    "构图要求（前+中+后）",
    "光影色彩 风格",
    "物理/AI 约束",
    "修改建议落地",
]

HEADER_ALIASES = {
    "#": {"#", "序号", "编号"},
    "场次-镜号": {"场次-镜号", "场次镜号", "场次/镜号", "场号-镜号", "镜号"},
    "画面核心内容": {"画面核心内容", "画面内容", "核心画面", "镜头内容"},
    "光学参数": {"光学参数", "镜头参数", "焦段", "光圈", "镜头/光学参数"},
    "景别": {"景别", "镜头类型", "镜头类型/景别", "景别/镜头"},
    "运镜调度": {"运镜调度", "运镜", "摄影机运动", "人物调度"},
    "构图要求（前+中+后）": {"构图要求（前+中+后）", "构图要求", "前中后景", "前+中+后"},
    "光影色彩 风格": {"光影色彩 风格", "光影色彩风格", "光影色彩", "色彩风格", "影调风格"},
    "物理/AI 约束": {"物理/AI 约束", "物理AI约束", "物理约束", "AI约束", "约束"},
    "修改建议落地": {"修改建议落地", "修改建议", "落地建议"},
}


class StoryboardXlsxStage(PromptStage):
    def save_content(self, state: ProjectState, content: str) -> str:
        output_path = Path(state["output_dir"]) / self.output_filename
        write_storyboard_xlsx(content, output_path)
        return str(output_path.resolve())


def make_storyboard_stage(prompt_dir: Path, llm: LLMClient, storage: ProjectStorage) -> PromptStage:
    return StoryboardXlsxStage(
        name="storyboard",
        prompt_file="storyboard_prompt2.txt",
        output_key="storyboard",
        output_filename="06_storyboard.xlsx",
        prompt_dir=prompt_dir,
        llm=llm,
        storage=storage,
        placeholders={"scene_write": "final_script"},
        system_prompt="你是一名从业数十年的顶级电影导演。严格遵守用户给定提示词，不改变原意。",
    )


def write_storyboard_xlsx(csv_content: str, output_path: Path) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover - depends on local env
        raise RuntimeError("Package 'openpyxl' is missing. Run: pip install -r requirements.txt") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = normalize_storyboard_rows(csv_content)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "分镜表"
    worksheet.sheet_view.showGridLines = False

    for row in rows:
        worksheet.append(row if row else [""] * len(HEADERS))

    thin_side = Side(style="thin", color="B8C2CC")
    grid_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    header_fill = PatternFill("solid", fgColor="E7EBF0")
    body_fill = PatternFill("solid", fgColor="FFFFFF")
    header_font = Font(name="Microsoft YaHei", bold=True, color="44505C", size=11)
    body_font = Font(name="Microsoft YaHei", color="5F6B7A", size=10)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    body_alignment = Alignment(vertical="top", wrap_text=True)

    widths = [6, 16, 44, 22, 14, 26, 34, 24, 30, 24]
    for index, width in enumerate(widths, start=1):
        worksheet.column_dimensions[get_column_letter(index)].width = width

    blank_rows = {
        row_index
        for row_index in range(2, worksheet.max_row + 1)
        if all((worksheet.cell(row=row_index, column=column).value or "") == "" for column in range(1, len(HEADERS) + 1))
    }

    for row in worksheet.iter_rows(min_row=1, max_row=worksheet.max_row, max_col=len(HEADERS)):
        row_index = row[0].row
        is_header = row_index == 1
        is_blank = row_index in blank_rows
        worksheet.row_dimensions[row_index].height = 10 if is_blank else (28 if is_header else 58)

        for cell in row:
            if is_blank:
                cell.border = Border()
                cell.fill = body_fill
                continue

            cell.border = grid_border
            cell.fill = header_fill if is_header else body_fill
            cell.font = header_font if is_header else body_font
            cell.alignment = header_alignment if is_header else body_alignment

    worksheet.freeze_panes = "A2"
    workbook.save(output_path)


def normalize_storyboard_rows(content: str) -> list[list[str]]:
    rows = parse_csv_rows(strip_code_fence(content))
    if not rows:
        return [HEADERS]

    first_nonblank = next((row for row in rows if row), None)
    if first_nonblank is None:
        return [HEADERS]

    normalized: list[list[str]] = []
    if is_header_row(first_nonblank):
        header_consumed = False
        for row in rows:
            if row and not header_consumed and is_header_row(row):
                normalized.append(HEADERS)
                header_consumed = True
                continue
            normalized.append(normalize_data_row(row) if row else [])
    else:
        normalized.append(HEADERS)
        normalized.extend(normalize_data_row(row) if row else [] for row in rows)

    return normalized


def parse_csv_rows(content: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(content))
    rows: list[list[str]] = []
    for row in reader:
        cleaned = [cell.strip() for cell in row]
        if not cleaned or all(cell == "" for cell in cleaned):
            rows.append([])
        else:
            rows.append(cleaned)
    return rows


def normalize_data_row(row: list[str]) -> list[str]:
    if len(row) == len(HEADERS) - 1:
        return normalize_row(row + [""])
    return normalize_row(row)


def normalize_row(row: list[str]) -> list[str]:
    values = row[: len(HEADERS)]
    if len(values) < len(HEADERS):
        values.extend([""] * (len(HEADERS) - len(values)))
    values[-1] = ""
    return values


def is_header_row(row: list[str]) -> bool:
    normalized_cells = {normalize_header_cell(cell) for cell in row if cell.strip()}
    if not normalized_cells:
        return False

    matches = 0
    for header, aliases in HEADER_ALIASES.items():
        possible = {normalize_header_cell(value) for value in aliases | {header}}
        if normalized_cells & possible:
            matches += 1
    return matches >= 5


def normalize_header_cell(value: str) -> str:
    return (
        value.strip()
        .replace(" ", "")
        .replace("\t", "")
        .replace("|", "")
        .replace("(", "（")
        .replace(")", "）")
        .lower()
    )


def strip_code_fence(content: str) -> str:
    text = content.strip().lstrip("\ufeff")
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
