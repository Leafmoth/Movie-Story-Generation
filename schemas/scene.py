from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Scene(BaseModel):
    number: int
    interior_exterior: str
    location: str
    time: str
    summary: str
    content: Optional[str] = None
