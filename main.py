from __future__ import annotations

import argparse

from core.orchestrator import StoryOrchestrator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the movie screenplay generation pipeline locally.")
    parser.add_argument("--logline", required=True, help="用户输入的一句话概括")
    parser.add_argument("--duration", required=True, type=int, help="影片时长，单位分钟")
    parser.add_argument("--theme", default="", help="主题问题，可不填")
    parser.add_argument("--genre", default="", help="影片类型，可不填")
    parser.add_argument("--project-id", default=None, help="输出项目目录名，可不填")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    orchestrator = StoryOrchestrator()
    state = orchestrator.generate(
        {
            "logline": args.logline,
            "duration_minutes": args.duration,
            "theme_question": args.theme,
            "genre": args.genre,
            "project_id": args.project_id,
        }
    )
    print(f"project_id: {state['project_id']}")
    print(f"output_dir: {state['output_dir']}")
    print(f"final_script: {state.get('stage_files', {}).get('final_script', '')}")


if __name__ == "__main__":
    main()
