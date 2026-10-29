import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import set_chat_service
from app.api.routes import router
from app.chat.service import ChatService
from app.core.config import settings
from app.core.exceptions import AppError

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core import config
    config.settings = config.Settings(_env_file=".env")
    service = ChatService()
    await service.startup()
    set_chat_service(service)
    yield
    await service.shutdown()


app = FastAPI(title="MyNaksh Personalized Astrology Chat", lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception occurred: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": "An unexpected error occurred."},
    )


app.include_router(router)
