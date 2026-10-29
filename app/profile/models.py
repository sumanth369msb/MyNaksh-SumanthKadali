from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class UserProfile(BaseModel):
    user_id: str
    name: Optional[str] = None
    date_of_birth: Optional[date] = None
    time_of_birth: Optional[str] = None
    birth_place: Optional[str] = None
    preferred_language: Optional[str] = None
    zodiac: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _validate_dob(cls, v: Any) -> Any:
        if v is None or isinstance(v, date):
            return v
        from app.llm.prompts import parse_flexible_date

        parsed = parse_flexible_date(v)
        return parsed if parsed is not None else v


# ProfileUpdate is unified with ProfilePayload to eliminate duplicate model definitions
# between API schemas and domain models while maintaining backward compatibility.
from app.api.schemas import ProfilePayload as ProfileUpdate
