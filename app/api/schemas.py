from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    profile: Optional[dict] = None

    @field_validator("user_id", "session_id", "message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace")
        return v.strip()


class ProfilePayload(BaseModel):
    name: Optional[str] = None
    date_of_birth: Optional[date] = None
    time_of_birth: Optional[str] = None
    birth_place: Optional[str] = None
    preferred_language: Optional[str] = None
    zodiac: Optional[str] = None
    metadata: Optional[dict] = None

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _validate_dob(cls, v):
        if v is None or isinstance(v, date):
            return v
        from app.llm.prompts import parse_flexible_date

        parsed = parse_flexible_date(v)
        return parsed if parsed is not None else v


class CreateUserRequest(BaseModel):
    user_id: str = Field(min_length=1)
    profile: Optional[ProfilePayload] = None

    @field_validator("user_id")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace")
        return v.strip()


class ChatResponse(BaseModel):
    response: str
    user_id: str
    session_id: str
    context_used: list[str] = Field(default_factory=list)
