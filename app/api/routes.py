from typing import Optional

from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_chat_service
from app.api.schemas import ChatRequest, ChatResponse, CreateUserRequest
from app.core.exceptions import AppError
from app.profile.models import UserProfile

router = APIRouter()


@router.get("/health")
async def health():
    service = get_chat_service()
    from app.core.config import settings
    return {
        "status": "ok",
        "backend": settings.graph_backend,
        "store": type(service.graph_store).__name__,
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    service = get_chat_service()
    profile = None
    if request.profile:
        try:
            profile = UserProfile(user_id=request.user_id, **request.profile)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    try:
        result = await service.chat(request.user_id, request.session_id, request.message, profile)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ChatResponse(**result)


@router.post("/users")
async def create_user(request: CreateUserRequest):
    service = get_chat_service()
    profile = None
    if request.profile:
        profile = UserProfile(user_id=request.user_id, **request.profile.model_dump(exclude_none=True))
        if profile.date_of_birth is not None:
            from app.astrology.calculator import compute_zodiac

            profile.zodiac = compute_zodiac(profile.date_of_birth)
    try:
        user_to_upsert = profile or UserProfile(user_id=request.user_id)
        await service.graph_store.upsert_user(user_to_upsert)
        saved_profile = await service.graph_store.get_user(request.user_id) or user_to_upsert
        if saved_profile is not None:
            await service.sync_profile_facts(saved_profile)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"user_id": request.user_id, "status": "created"}


@router.get("/users/{user_id}")
async def get_user(user_id: str):
    service = get_chat_service()
    try:
        profile = await service.graph_store.get_user(user_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    return profile.model_dump(mode="json")


@router.get("/users/{user_id}/brain")
async def get_brain(user_id: str):
    service = get_chat_service()
    try:
        facts = await service.graph_store.get_facts(user_id, limit=100)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"user_id": user_id, "facts": [f.model_dump(mode="json") for f in facts]}
