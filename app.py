from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from core.orchestrator import StoryOrchestrator
from schemas.story import StoryboardGenerationRequest, StoryGenerationRequest, StoryGenerationResponse, response_from_state


app = FastAPI(title="Movie Story Generation", version="0.1.0")
orchestrator = StoryOrchestrator()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", response_model=StoryGenerationResponse)
def generate_story(request: StoryGenerationRequest) -> StoryGenerationResponse:
    try:
        payload = request.model_dump()
    except AttributeError:  # pydantic v1 fallback
        payload = request.dict()

    try:
        state = orchestrator.generate(payload, include_storyboard=payload.get("include_storyboard", True))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return response_from_state(state)


@app.post("/generate/script-only", response_model=StoryGenerationResponse)
def generate_script_only(request: StoryGenerationRequest) -> StoryGenerationResponse:
    try:
        payload = request.model_dump()
    except AttributeError:  # pydantic v1 fallback
        payload = request.dict()

    try:
        state = orchestrator.generate(payload, include_storyboard=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return response_from_state(state)


@app.post("/storyboard", response_model=StoryGenerationResponse)
def generate_storyboard(request: StoryboardGenerationRequest) -> StoryGenerationResponse:
    try:
        payload = request.model_dump()
    except AttributeError:  # pydantic v1 fallback
        payload = request.dict()

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
