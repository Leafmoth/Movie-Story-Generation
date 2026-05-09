from __future__ import annotations

from typing import List

from pydantic import BaseModel


class OutlineBeat(BaseModel):
    title: str
    summary: str
    act: str


class StoryOutline(BaseModel):
    duration_minutes: int
    beats: List[OutlineBeat]
