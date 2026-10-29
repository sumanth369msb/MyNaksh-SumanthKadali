from fastapi.testclient import TestClient


def _chat(client: TestClient, user_id, session_id, message, profile=None):
    payload = {"user_id": user_id, "session_id": session_id, "message": message}
    if profile:
        payload["profile"] = profile
    return client.post("/chat", json=payload)


def test_new_user_basic(client: TestClient):
    r = _chat(client, "u1", "s1", "Hello")
    assert r.status_code == 200
    data = r.json()
    assert data["response"]
    assert data["user_id"] == "u1"


def test_create_long_term_memory(client: TestClient):
    r = _chat(
        client,
        "u2",
        "s1",
        "My name is Rahul. I was born on 15 August 1995 in Delhi. I'm planning to switch jobs next year.",
        profile={"date_of_birth": "1995-08-15", "birth_place": "Delhi", "preferred_language": "Hindi"},
    )
    assert r.status_code == 200
    brain = client.get("/users/u2/brain").json()
    types = {f["type"] for f in brain["facts"]}
    assert "goal" in types
    assert "profile" in types


def test_retrieve_memory_new_session(client: TestClient):
    _chat(client, "u3", "s1", "I'm planning to switch jobs next year.")
    r = _chat(client, "u3", "s2", "What do you remember about my career goals?")
    assert r.status_code == 200
    data = r.json()
    assert "shared_brain" in data["context_used"] or "career_goal" in data["context_used"]


def test_followup_uses_conversation(client: TestClient):
    _chat(client, "u4", "s1", "What should I focus on for my career?")
    r = _chat(client, "u4", "s1", "Why do you say that?")
    assert r.status_code == 200
    assert "conversation_history" in r.json()["context_used"]


def test_career_question_uses_goal(client: TestClient):
    _chat(client, "u5", "s1", "I'm planning to switch jobs next year.")
    r = _chat(client, "u5", "s1", "What should I focus on for my career?")
    assert r.status_code == 200
    assert "career_goal" in r.json()["context_used"]


def test_missing_profile(client: TestClient):
    r = _chat(client, "u6", "s1", "What is my zodiac sign?")
    assert r.status_code == 200
    assert r.json()["response"]


def test_correction_updates_memory(client: TestClient):
    _chat(client, "u7", "s1", "I'm planning to switch jobs next year.")
    _chat(client, "u7", "s1", "Actually I will switch jobs in 2026.")
    brain = client.get("/users/u7/brain").json()
    goals = [f for f in brain["facts"] if f["type"] == "goal"]
    assert goals
    assert any("2026" in str(f.get("metadata", {})) or "2026" in f["value"] for f in goals)


def test_irrelevant_memory_not_selected(client: TestClient):
    _chat(client, "u8", "s1", "I love cooking Italian food.")
    r = _chat(client, "u8", "s1", "What should I focus on for my career?")
    assert r.status_code == 200
    assert "career_goal" not in r.json()["context_used"]


def test_user_creation_endpoint(client: TestClient):
    r = client.post("/users", json={"user_id": "u9", "profile": {"name": "Rahul", "date_of_birth": "1995-08-15", "birth_place": "Delhi"}})
    assert r.status_code == 200
    g = client.get("/users/u9").json()
    assert g["name"] == "Rahul"
    assert g["zodiac"] == "Leo"


def test_health(client: TestClient):
    assert client.get("/health").json()["status"] == "ok"
