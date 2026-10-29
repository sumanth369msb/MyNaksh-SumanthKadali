from __future__ import annotations

from app.chat.service import ChatService

_chat_service: ChatService | None = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        from app.chat.service import ChatService

        _chat_service = ChatService()
    return _chat_service


def set_chat_service(service: ChatService) -> None:
    global _chat_service
    _chat_service = service
