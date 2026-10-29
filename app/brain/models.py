from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class MemoryFact(BaseModel):
    id: Optional[str] = None
    user_id: str
    type: str
    key: str
    value: str
    relation: str = "HAS_FACT"
    confidence: float = 0.8
    source: str = "conversation"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CandidateFact(BaseModel):
    type: str
    key: str
    value: str
    relation: str = "HAS_FACT"
    confidence: float = 0.8
    source: str = "conversation"
    metadata: dict[str, Any] = Field(default_factory=dict)
