from __future__ import annotations

from fastapi import FastAPI, HTTPException

from core.orchestrator import StoryOrchestrator
from schemas.story import StoryGenerationRequest, StoryGenerationResponse, response_from_state


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
        state = orchestrator.generate(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return response_from_state(state)
