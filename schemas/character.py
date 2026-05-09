from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CharacterProfile(BaseModel):
    name: str
    role_type: str
    surface_want: Optional[str] = None
    true_need: Optional[str] = None
    fear: Optional[str] = None
    false_belief: Optional[str] = None
    arc: Optional[str] = None
