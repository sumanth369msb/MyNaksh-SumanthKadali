# Repository Architecture & Onboarding Guide

## What This Repository Is

This repository implements **MyNaksh Personalized Astrology Chat** — a production-oriented conversational AI service that combines short-term conversation memory with a persistent graph-based Shared Brain (long-term user memory) to deliver personalized astrology and life-guidance responses.

The system is built with **FastAPI** (Python 3.9+), uses **Neo4j** (or an in-memory graph fallback) for long-term memory storage, and integrates with an **LLM provider** (OpenAI-compatible or a deterministic mock for testing).

## Why This Architecture Was Chosen

| Decision | Rationale |
|---|---|
| Graph database (Neo4j) for Shared Brain | User context in astrology is inherently multi-relational (goals, interests, preferences, zodiac linked to life areas). Graph traversal enables targeted neighborhood queries without loading the entire user profile into the LLM prompt. |
| Short-term vs long-term memory separation | Follow-up questions ("Why do you say that?") need recent conversation context, not the full graph. Persistent facts (goals, profile) must survive across sessions. |
| Pluggable LLM provider | Allows swapping OpenAI, local models, or a deterministic mock without rewriting application logic. Critical for testing without API keys. |
| Rule-based + optional LLM extraction | Avoids over-engineering; durable facts are extracted deterministically, with optional LLM enhancement when a real provider is configured. |
| In-memory graph fallback | Enables zero-dependency testing and graceful degradation when Neo4j is unavailable. |

## System Design Overview

### Request Flow

```
POST /chat
  1. Validate input (Pydantic → 422 on blank/invalid)
  2. Upsert user profile into Shared Brain graph
  3. Append user turn to short-term session memory
  4. Extract durable facts from user message (rules + optional LLM)
  5. Upsert facts into Shared Brain (conflict resolution by type+key)
  6. Select relevant context (profile + top-K facts + recent turns)
  7. Build LLM prompt from current message + selected context only
  8. Generate response via LLM (cached; fallback on failure)
  9. Append assistant turn to short-term memory
  10. Return response + context_used audit trail
```

### Component Map

```
app/
├── main.py              # FastAPI app, lifespan
├── core/
│   ├── config.py        # Pydantic settings from .env
│   ├── exceptions.py    # AppError hierarchy (400, 404, 422, 429, 502, 503)
│   └── cache.py         # TTL cache for LLM responses
├── api/
│   ├── routes.py        # /health, /chat, /users, /users/{id}/brain
│   ├── schemas.py       # Request/response Pydantic models
│   └── dependencies.py  # ChatService singleton
├── chat/
│   └── service.py       # Orchestrator: profile → extract → select → generate → update
├── llm/
│   ├── base.py          # Provider protocol
│   ├── factory.py       # Provider selection from config
│   ├── mock.py          # Deterministic test provider
│   └── openai.py        # OpenAI-compatible client with retry/backoff
├── memory/
│   ├── extractor.py     # Rule-based + optional LLM fact extraction
│   └── short_term.py    # Per-session TTL sliding window
├── brain/
│   ├── models.py        # MemoryFact, CandidateFact
│   ├── store.py         # GraphStore protocol + InMemoryGraphStore
│   ├── neo4j_store.py   # Neo4j async driver implementation
│   └── factory.py       # Backend selection (memory vs neo4j)
├── context/
│   └── selector.py      # Fact scoring and top-K selection
├── profile/
│   └── models.py        # UserProfile, ProfileUpdate
└── astrology/
    └── calculator.py    # Stubbed Sun sign computation
```

### Data Flow: Memory Lifecycle

1. **Input:** User sends a message with optional profile.
2. **Extraction:** Rule-based extractor identifies durable facts (name, DOB, birth place, goals, interests, preferences). Greetings and meta-questions are filtered.
3. **Persistence:** Facts are upserted into the graph keyed by `(user_id, type, key)`. Conflicting values are overwritten in place.
4. **Selection:** On the next message, facts are scored against the query using token overlap, type/keyword boosts, confidence, and recency. Only top-K relevant facts are sent to the LLM.
5. **Response:** LLM generates a personalized response using selected context only.
6. **Update:** Short-term memory records the exchange; long-term memory is updated if new durable facts were extracted.

## Testing & Validation Objectives

### Test Coverage Map

| Test File | Scenarios Covered |
|---|---|
| `tests/test_chat.py` | New user, memory creation, retrieval, follow-up, new-session persistence, irrelevant memory filtering, correction, missing profile, user creation, health |
| `tests/test_production.py` | Blank/missing input (422), LLM failure fallback, graph failure fallback, extractor ignore/extract, correction dedup, session isolation, cache set/get/clear, 429 retry exhaustion, Neo4j graceful skip, protocol compliance |

### How to Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m pytest -q        # 22 passed, 1 skipped (Neo4j unavailable)
uvicorn app.main:app --reload
```

## Key Design Decisions for SDETs/QE

1. **Deterministic mock LLM:** All tests use `MockLLMProvider` so no API keys are needed. Responses are predictable and assertable.
2. **In-memory graph store:** Tests use `InMemoryGraphStore` to avoid Neo4j dependency. State is reset per test via `conftest.py`.
3. **Async throughout:** All store and LLM operations are async. Tests use `pytest-asyncio` for async test functions.
4. **Conflict resolution by key:** Memory updates overwrite in place by `(type, key)`, ensuring corrections don't create duplicates.
5. **Context isolation:** Short-term memory is session-scoped; long-term memory is user-scoped.
6. **Graceful degradation:** LLM and graph failures return fallback responses instead of 500 errors.

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| GRAPH_BACKEND | memory | `memory` or `neo4j` |
| LLM_PROVIDER | mock | `mock` or `openai` |
| MEMORY_TOP_K | 5 | Max facts sent to LLM |
| SHORT_TERM_MAX_MESSAGES | 20 | Short-term window size |
| CACHE_TTL_SECONDS | 300 | LLM response cache TTL |

## Known Limitations

- Neo4j integration is untested in CI (requires live database).
- No authentication/rate limiting by default.
- Facts are capped at 50 per user before context selection (increased to 200 in audit fixes, reverted).
- No pagination for large fact sets.
- Cache eviction is O(n) (acceptable for current scale).