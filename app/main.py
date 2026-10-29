import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dependencies import get_chat_service, set_chat_service
from app.api.routes import router
from app.chat.service import ChatService
from app.core.config import settings

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    service = ChatService()
    await service.startup()
    set_chat_service(service)
    yield
    await service.shutdown()


app = FastAPI(title="MyNaksh Personalized Astrology Chat", lifespan=lifespan)
app.include_router(router)
