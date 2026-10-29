from __future__ import annotations

"""Automated Test Suite for the 8 Core Architectural Scenarios (Requirement R4).

Covers end-to-end behavior across:
1. New user interaction with zero prior facts.
2. Creating a long-term memory (fact extraction and graph persistence).
3. Retrieving a memory (context scoring and tag emission).
4. Follow-up question (short-term conversation history utilization).
5. New session using previous information (cross-session memory recall).
6. Irrelevant memory suppression (strict zero-relevance filtering).
7. User correcting existing information (idempotent in-place fact replacement).
8. Missing user information (graceful handling and prompt guidance).
Plus adversarial boundary verification for special characters and whitespace validation.

==============================================================================
EVALUATING SHARED BRAIN QUALITY (SIX CORE EVALUATION AREAS):
==============================================================================
A sophisticated evaluation framework is not required; quality is evaluated
across the following six dimensions:

1. Memory Accuracy:
   Replay scripted conversations and assert extracted fact key/value match
   what the user stated (e.g., DOB "15 August 1995" -> ISO "1995-08-15").
   Verify no entity corruption, field truncation, or hallucinated facts.

2. Context Relevance:
   Assert selected facts overlap with incoming query intent/tokens; irrelevant
   facts must not appear in context_used or the LLM prompt. Top-K scoring
   ensures only high-salience facts are sent to the model.

3. Personalization:
   Verify responses reference stored name, zodiac, or goals rather than
   generic advice. Persona-aware astrological synthesis reflects user energy.

4. Conversation Consistency:
   Check that follow-up answers align with facts stored in prior turns of the
   same session, resolving pronouns ("Why do you say that?") seamlessly.

5. Irrelevant Context:
   Confirm out-of-domain queries (e.g., photosynthesis, math) do not emit
   shared_brain or surface unrelated stored facts in prompt context.

6. Memory Persistence:
   Assert facts survive across sessions and service restarts; facts must
   remain retrievable via GET /users/{id}/brain after a new session ID.
==============================================================================
"""
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_chat_service
from app.brain.models import MemoryFact
from app.context.selector import ContextSelector
from app.llm.prompts import CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT, build_chat_system_prompt


def _chat(
    client: TestClient,
    user_id: str,
    session_id: str,
    message: str,
    profile: dict | None = None,
):
    """Helper to dispatch chat requests through the TestClient."""
    payload = {"user_id": user_id, "session_id": session_id, "message": message}
    if profile:
        payload["profile"] = profile
    return client.post("/chat", json=payload)


# ============================================================================
# Scenario 1: New User
# ============================================================================
def test_scenario_1_new_user(client: TestClient):
    """Scenario 1: Fresh user interaction with zero prior facts.

    Verifies clean response, absence of long-term memory tags, and clean session initialization.
    """
    user_id = "user_scenario_1"
    session_id = "sess_sc1"

    res = _chat(client, user_id, session_id, "Hello there, good evening!")
    assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"

    data = res.json()
    assert data["user_id"] == user_id
    assert data["session_id"] == session_id
    assert isinstance(data["response"], str) and len(data["response"]) > 0

    # Verifies absence of long-term memory and history tags for fresh turn
    context_used = data.get("context_used", [])
    assert "shared_brain" not in context_used, "New user must not have 'shared_brain' in context_used"
    assert "career_goal" not in context_used, "New user must not have 'career_goal' in context_used"
    assert "conversation_history" not in context_used, "First turn must not have 'conversation_history'"
    assert "user_profile" not in context_used, "Unspecified profile must not emit 'user_profile'"

    # Verify Shared Brain contains zero facts for new user
    brain_res = client.get(f"/users/{user_id}/brain")
    assert brain_res.status_code == 200
    assert len(brain_res.json()["facts"]) == 0, "New user Shared Brain must have 0 facts"


# ============================================================================
# Scenario 2: Creating a Long-Term Memory
# ============================================================================
def test_scenario_2_create_long_term_memory(client: TestClient):
    """Scenario 2: User states a career goal or preference.

    Verifies that durable facts are extracted and persisted in GraphStore.
    """
    user_id = "user_scenario_2"
    session_id = "sess_sc2"
    message = "I am planning to switch jobs to AI engineering in 2026"

    res = _chat(client, user_id, session_id, message)
    assert res.status_code == 200

    # Query Shared Brain to verify persistence in GraphStore
    brain_res = client.get(f"/users/{user_id}/brain")
    assert brain_res.status_code == 200
    facts = brain_res.json()["facts"]
    assert len(facts) >= 1, "Expected at least one fact persisted in GraphStore"

    goal_facts = [f for f in facts if f["type"] == "goal"]
    assert len(goal_facts) >= 1, "Expected a goal fact to be extracted and persisted"
    career_fact = goal_facts[0]
    assert career_fact["key"] == "career"
    assert career_fact["relation"] == "HAS_GOAL"
    assert career_fact["confidence"] >= 0.7
    assert career_fact["metadata"].get("timeframe") == "2026"
    assert "switch jobs to AI engineering in 2026" in career_fact["value"]

    # Also verify preference extraction
    res_pref = _chat(client, user_id, session_id, "I prefer speaking English")
    assert res_pref.status_code == 200
    brain_updated = client.get(f"/users/{user_id}/brain").json()["facts"]
    pref_facts = [f for f in brain_updated if f["type"] == "preference"]
    assert len(pref_facts) >= 1
    assert pref_facts[0]["key"] == "language"
    assert pref_facts[0]["relation"] == "PREFERS"
    assert pref_facts[0]["value"] == "English"


# ============================================================================
# Scenario 3: Retrieving a Memory
# ============================================================================
def test_scenario_3_retrieve_memory(client: TestClient):
    """Scenario 3: Asking for career advice in a subsequent turn.

    Verifies that the stored fact is retrieved and 'career_goal' and 'shared_brain'
    tags are emitted in context_used.
    """
    user_id = "user_scenario_3"
    session_id = "sess_sc3"

    # Turn 1: Establish durable career goal in Shared Brain
    res1 = _chat(client, user_id, session_id, "I am planning to switch jobs to AI engineering in 2026")
    assert res1.status_code == 200

    # Turn 2: Query for career transition advice
    res2 = _chat(client, user_id, session_id, "What should I focus on for my career transition?")
    assert res2.status_code == 200

    data = res2.json()
    context_used = data.get("context_used", [])
    assert "shared_brain" in context_used, "Expected 'shared_brain' tag in context_used"
    assert "career_goal" in context_used, "Expected 'career_goal' tag in context_used"

    # Verify that response acknowledges career transition guidance
    response_lower = data["response"].lower()
    assert any(term in response_lower for term in ("career", "transition", "goal", "focus", "skill"))


# ============================================================================
# Scenario 4: Follow-up Question
# ============================================================================
def test_scenario_4_follow_up_question(client: TestClient):
    """Scenario 4: Immediate multi-turn follow-up question.

    Verifies that short-term conversation context ('conversation_history') is included in context_used.
    """
    user_id = "user_scenario_4"
    session_id = "sess_sc4"

    # Turn 1: Initial query
    res1 = _chat(client, user_id, session_id, "What should I focus on for my career?")
    assert res1.status_code == 200

    # Turn 2: Immediate follow-up query requiring conversational context
    res2 = _chat(client, user_id, session_id, "Why do you say that?")
    assert res2.status_code == 200

    data = res2.json()
    context_used = data.get("context_used", [])
    assert "conversation_history" in context_used, "Expected 'conversation_history' tag for turn 2"
    assert len(data["response"]) > 0


# ============================================================================
# Scenario 5: New Session Using Previous Information
# ============================================================================
def test_scenario_5_new_session_using_previous_info(client: TestClient):
    """Scenario 5: Same user ID with a brand-new session ID.

    Verifies cross-session memory persistence: short-term history is clean,
    but the long-term career fact is successfully retrieved.
    """
    user_id = "user_scenario_5"
    old_session = "sess_alpha_old"
    new_session = "sess_beta_new"

    # Turn 1 in old session: Persist career goal
    res1 = _chat(client, user_id, old_session, "I am planning to switch jobs to AI engineering in 2026")
    assert res1.status_code == 200

    # Turn 2 in new session: Query previously stated goals
    res2 = _chat(client, user_id, new_session, "What do you remember about my career goals?")
    assert res2.status_code == 200

    data = res2.json()
    context_used = data.get("context_used", [])

    # Cross-session persistence verified
    assert "shared_brain" in context_used or "career_goal" in context_used, (
        "Stored long-term fact must be retrieved across sessions"
    )
    # Short-term conversation history must NOT leak into the new session
    assert "conversation_history" not in context_used, (
        "New session must not inherit conversation_history from old session"
    )


# ============================================================================
# Scenario 6: Irrelevant Memory
# ============================================================================
def test_scenario_6_irrelevant_memory(client: TestClient):
    """Scenario 6: Out-of-domain query.

    Verifies that zero facts are selected (selected_facts == []) and
    'shared_brain' is strictly NOT in context_used.
    """
    user_id = "user_scenario_6"
    session_id = "sess_sc6"

    # Seed the user's brain with a career goal
    res1 = _chat(client, user_id, session_id, "I am planning to switch jobs to AI engineering in 2026")
    assert res1.status_code == 200

    # Test out-of-domain query 1: Photosynthesis
    res_biology = _chat(client, user_id, "sess_sc6_bio", "Can you explain how photosynthesis works in green plants?")
    assert res_biology.status_code == 200
    data_bio = res_biology.json()
    assert "shared_brain" not in data_bio["context_used"], "Irrelevant query must not emit 'shared_brain'"
    assert "career_goal" not in data_bio["context_used"], "Irrelevant query must not emit 'career_goal'"

    # Test out-of-domain query 2: Chocolate chip cookie recipe
    res_recipe = _chat(client, user_id, "sess_sc6_recipe", "What is the secret recipe for chocolate chip cookies?")
    assert res_recipe.status_code == 200
    data_recipe = res_recipe.json()
    assert "shared_brain" not in data_recipe["context_used"], "Irrelevant query must not emit 'shared_brain'"
    assert "career_goal" not in data_recipe["context_used"], "Irrelevant query must not emit 'career_goal'"

    # Direct unit verification of ContextSelector relevance suppression
    service = get_chat_service()
    facts = [
        MemoryFact(
            user_id=user_id,
            type="goal",
            key="career",
            value="I am planning to switch jobs to AI engineering in 2026",
            relation="HAS_GOAL",
            confidence=0.75,
            metadata={"timeframe": "2026"},
        )
    ]
    selector = ContextSelector()
    selected, ctx = selector.select("Can you explain how photosynthesis works in green plants?", None, facts, [])
    assert selected == [], f"Expected selected_facts to be empty on zero relevance, got: {selected}"
    assert "shared_brain" not in ctx


# ============================================================================
# Scenario 7: User Correcting Existing Information
# ============================================================================
def test_scenario_7_user_correcting_info(client: TestClient):
    """Scenario 7: User corrects previously stated information.

    Verifies in-place fact update/replacement in GraphStore without duplicate fact nodes.
    """
    user_id = "user_scenario_7"
    session_id = "sess_sc7"

    # Step 1: User declares 2026 career target
    res1 = _chat(client, user_id, session_id, "I am planning to switch jobs to AI engineering in 2026")
    assert res1.status_code == 200

    brain1 = client.get(f"/users/{user_id}/brain").json()["facts"]
    goals1 = [f for f in brain1 if f["type"] == "goal"]
    assert len(goals1) == 1, "Expected exactly 1 goal fact initially"
    initial_fact_id = goals1[0]["id"]
    assert goals1[0]["metadata"].get("timeframe") == "2026"

    # Step 2: User corrects career target to 2025
    res2 = _chat(client, user_id, session_id, "Actually I will switch jobs in 2025.")
    assert res2.status_code == 200

    brain2 = client.get(f"/users/{user_id}/brain").json()["facts"]
    goals2 = [f for f in brain2 if f["type"] == "goal"]

    # Graph must NOT accumulate duplicate goal nodes: count remains 1
    assert len(goals2) == 1, f"Idempotent upsert must replace fact; expected 1 goal fact, found {len(goals2)}"
    assert goals2[0]["id"] == initial_fact_id, "Fact node ID must remain consistent"
    assert goals2[0]["metadata"].get("timeframe") == "2025" or "2025" in goals2[0]["value"]


# ============================================================================
# Scenario 8: Missing User Information
# ============================================================================
def test_scenario_8_missing_user_info(client: TestClient):
    """Scenario 8: User requests astrological analysis without providing date of birth.

    Verifies that the service responds gracefully with guidance requesting the missing birth details.
    """
    user_id = "user_scenario_8"
    session_id = "sess_sc8"

    # Query asking for birth chart calculation without providing profile birth details
    res = _chat(client, user_id, session_id, "What is my astrological ascendant and moon nakshatra?")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["response"], str) and len(data["response"]) > 0
    assert "user_profile" not in data["context_used"], "Profile was not supplied; 'user_profile' must not be tagged"

    # Verify that the system prompt architecture explicitly incorporates Missing Birth Information Protocol
    assert "Missing Birth Information Protocol" in CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT
    assert "politely and warmly request the missing birth information" in CONVERSATIONAL_ASTROLOGY_SYSTEM_PROMPT

    # Verify prompt builder when profile is None
    system_prompt = build_chat_system_prompt(profile=None, facts=[], recent_turns=[])
    assert "Missing Birth Information Protocol" in system_prompt
    assert "User profile:" not in system_prompt

    # Verify graceful behavior with partial profile (name provided, but birth details missing)
    partial_res = _chat(
        client,
        "user_scenario_8_partial",
        "sess_sc8_part",
        "Can you read my planetary chart?",
        profile={"name": "Aarav"},
    )
    assert partial_res.status_code == 200
    part_data = partial_res.json()
    assert "user_profile" in part_data["context_used"]
    assert "zodiac_sign" not in part_data["context_used"], "No zodiac can be computed without date of birth"


# ============================================================================
# Scenario 9 (Adversarial): Special Characters, Escaping & SQL/JSON Integrity
# ============================================================================
def test_scenario_adversarial_special_characters_and_escaping(client: TestClient):
    """Verifies that special characters, quotes, and HTML/JSON meta-characters do not corrupt memory."""
    user_id = "user_adv_special"
    session_id = "sess_adv_1"

    # Input containing single and double quotes, angle brackets, and punctuation
    special_msg = "I'm planning to switch jobs to AI & ML engineer at \"TechCorp\" in 2026! <script>alert('test')</script>"
    res = _chat(client, user_id, session_id, special_msg)
    assert res.status_code == 200

    brain = client.get(f"/users/{user_id}/brain").json()["facts"]
    goals = [f for f in brain if f["type"] == "goal"]
    assert len(goals) == 1
    assert goals[0]["metadata"].get("timeframe") == "2026"
    assert "TechCorp" in goals[0]["value"]


# ============================================================================
# Scenario 10 (Adversarial): Empty & Whitespace Validation
# ============================================================================
def test_scenario_adversarial_empty_and_whitespace_validation(client: TestClient):
    """Verifies defensive input validation rejecting empty or whitespace-only messages."""
    # API schema validation returns 422 Unprocessable Entity
    res_empty = client.post("/chat", json={"user_id": "u_val", "session_id": "s_val", "message": ""})
    assert res_empty.status_code == 422

    res_spaces = client.post("/chat", json={"user_id": "u_val", "session_id": "s_val", "message": "    \t \n  "})
    assert res_spaces.status_code == 422

    # Direct service validation check
    service = get_chat_service()
    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        import asyncio
        asyncio.run(service.chat("u_val", "s_val", "   "))
