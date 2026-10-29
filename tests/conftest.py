import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LLM_PROVIDER", "mock")

from app.api.dependencies import get_chat_service
from app.brain.store import InMemoryGraphStore
from app.main import app
from app.memory.short_term import ShortTermMemory


@pytest.fixture
def client():
    with TestClient(app) as c:
        service = get_chat_service()
        service.graph_store = InMemoryGraphStore()
        service.short_term = ShortTermMemory()
        service.cache.clear()
        yield c
