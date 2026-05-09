from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.orchestrator import StoryOrchestrator


COMMANDS = {"full", "script", "storyboard"}


def add_generation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--logline", required=True, help="用户输入的一句话概括")
    parser.add_argument("--duration", required=True, type=int, help="影片时长，单位分钟")
    parser.add_argument("--theme", default="", help="主题问题，可不填")
    parser.add_argument("--genre", default="", help="影片类型，可不填")
    parser.add_argument("--project-id", default=None, help="输出项目目录名，可不填")


def parse_args() -> argparse.Namespace:
    if len(sys.argv) > 1 and sys.argv[1] not in COMMANDS:
        sys.argv.insert(1, "full")

    parser = argparse.ArgumentParser(description="Run the movie screenplay generation pipeline locally.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    full_parser = subparsers.add_parser("full", help="从用户输入直接生成文学剧本和分镜表格")
    add_generation_args(full_parser)

    script_parser = subparsers.add_parser("script", help="只生成文学剧本，不生成分镜表格")
    add_generation_args(script_parser)

    storyboard_parser = subparsers.add_parser("storyboard", help="根据已生成的文学剧本继续生成分镜表格")
    storyboard_parser.add_argument("--project-dir", default=None, help="包含 final_script.md 的项目输出目录")
    storyboard_parser.add_argument("--script-path", default=None, help="已有 final_script.md 的路径")
    storyboard_parser.add_argument("--project-id", default=None, help="outputs 下的项目目录名")
    storyboard_parser.add_argument("--output-dir", default=None, help="分镜表格保存目录，默认跟随剧本所在目录")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    orchestrator = StoryOrchestrator()

    if args.command == "storyboard":
        state = run_storyboard_command(args, orchestrator)
    else:
        state = orchestrator.generate(
            {
                "logline": args.logline,
                "duration_minutes": args.duration,
                "theme_question": args.theme,
                "genre": args.genre,
                "project_id": args.project_id,
            },
            include_storyboard=args.command == "full",
        )

    print(f"project_id: {state['project_id']}")
    print(f"output_dir: {state['output_dir']}")
    print(f"final_script: {state.get('stage_files', {}).get('final_script', '')}")
    if state.get("stage_files", {}).get("storyboard"):
        print(f"storyboard: {state['stage_files']['storyboard']}")


def run_storyboard_command(args: argparse.Namespace, orchestrator: StoryOrchestrator) -> dict:
    script_path = resolve_script_path(args, orchestrator)
    if not script_path.exists():
        raise FileNotFoundError(f"final_script not found: {script_path}")

    final_script = script_path.read_text(encoding="utf-8")
    output_dir = args.output_dir or args.project_dir or str(script_path.resolve().parent)
    return orchestrator.generate_storyboard_from_script(
        final_script=final_script,
        project_id=args.project_id or Path(output_dir).name,
        output_dir=output_dir,
        final_script_path=str(script_path.resolve()),
    )


def resolve_script_path(args: argparse.Namespace, orchestrator: StoryOrchestrator) -> Path:
    if args.script_path:
        return Path(args.script_path).resolve()
    if args.project_dir:
        return (Path(args.project_dir) / "final_script.md").resolve()
    if args.project_id:
        return (orchestrator.settings.output_root / args.project_id / "final_script.md").resolve()
    raise ValueError("Provide --project-dir, --script-path, or --project-id for storyboard generation.")


if __name__ == "__main__":
    main()
