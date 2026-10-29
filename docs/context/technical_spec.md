# MyNaksh Personalized Astrology Chat — Technical Specification

Production-oriented conversational AI service built with FastAPI. It accepts a user profile and chat messages, maintains short-term conversation context, builds a persistent graph-based Shared Brain of long-term user facts, retrieves relevant Shared Brain context before calling a modular LLM layer, and updates memory after every response.

Python: 3.9+
Framework: FastAPI
LLM: OpenAI-compatible provider or built-in deterministic mock
Database: Neo4j (preferred) with an in-memory graph fallback for tests/development

---

## 1. Architecture

Request flow:

```
POST /chat
  ├─ 1. Validate input (Pydantic / 422 on blank fields)
  ├─ 2. Upsert user profile into Shared Brain graph
  ├─ 3. Append user turn to short-term session memory
  ├─ 4. Extract durable facts from the user message (rule-based + optional LLM)
  ├─ 5. Upsert extracted facts into Shared Brain with conflict resolution by (type, key)
  ├─ 6. Select relevant context: user profile + top-K Shared Brain facts + recent short-term turns
  ├─ 7. Build LLM prompt from current message + selected context only (never the full graph)
  ├─ 8. Generate response via pluggable LLM provider (cached; fallback on failure)
  ├─ 9. Append assistant turn to short-term session memory
  └─ 10. Return response, user_id, session_id, context_used
```

Key design decisions:
- Graph database preferred because astrology user context is multi-relational and neighborhood queries can be filtered by fact type without loading the entire user history into the LLM.
- Short-term memory is session-scoped and TTL-bounded; long-term memory is user-scoped and persisted in the graph.
- Only relevant facts are sent to the LLM using keyword/type/recency/confidence scoring.
- LLM provider is abstracted behind a protocol so OpenAI, local models, or the deterministic mock can be swapped without changing the application.
- LLM responses are cached by user, session, message, selected fact identifiers, and recent turn contents to reduce latency and cost.

---

## 2. Shared Brain Graph Schema

Nodes:
- `User { id, name, date_of_birth, time_of_birth, birth_place, preferred_language, zodiac, metadata }`
- `Fact { id, user_id, type, key, value, relation, confidence, source, metadata, created_at, updated_at }`

Relationships:
- `User -[:HAS_FACT]-> Fact`
- `Fact` relationship property `relation` stores the semantic edge (for example `HAS_GOAL`, `PREFERS`, `INTERESTED_IN`, `HAS_MEMORY`)

Example stored facts:
```
User
├── HAS_FACT -> Fact { type: profile, key: name, value: Rahul }
├── HAS_FACT -> Fact { type: profile, key: date_of_birth, value: 1995-08-15 }
├── HAS_FACT -> Fact { type: goal, key: career, value: switch jobs next year, metadata: { timeframe: 2027 } }
├── HAS_FACT -> Fact { type: preference, key: language, value: Hindi }
└── HAS_FACT -> Fact { type: zodiac, key: sun_sign, value: Leo }
```

Retrieval:
- Load facts for a user, optionally filtered by type.
- Score each fact against the current query using token overlap, type/keyword boosts, confidence, and recency.
- Return only the top-K facts to the LLM.

Conflict resolution:
- Upsert is keyed by `(user_id, type, key)`. A correction such as changing a job-switch year overwrites the existing fact in place instead of creating duplicates.

---

## 3. Memory Strategy

Short-term context:
- Per `session_id`, sliding window of the most recent messages.
- Used for referential follow-ups such as "Why do you say that?".
- TTL evicts inactive sessions.

Long-term memory:
- Persistent user facts stored in the Shared Brain graph.
- Not every message is stored; the extractor only writes durable facts such as name, date of birth, birth place, goals, interests, preferences, and zodiac attributes.
- Greetings, meta-questions, and low-signal turns are ignored by the rule-based extractor.

Memory update after each response:
- Extract candidate facts from the latest user message.
- For profile facts, merge into the `User` node and recompute zodiac if date of birth is present.
- For other facts, upsert into the graph by canonical key.

---

## 4. Context Selection

Input: current user message, user profile, all candidate facts, recent short-term turns.
Output: selected facts and `context_used` audit tags.

Scoring:
- Token overlap between query and fact text.
- Boosts for domain keyword matches: career/job/interview match goal facts; language/prefer match preference facts.
- Confidence and recency weighting.
- Top-K selection; falls back to most recent facts when nothing scores above zero.

Context tags include:
- `user_profile`
- `shared_brain`
- `conversation_history`
- `career_goal`
- `language_preference`

---

## 5. LLM Layer

Provider protocol:
- `generate(messages, temperature, max_tokens) -> str`
- Optional `extract_facts(text) -> list[dict]`

Providers:
- `MockLLMProvider`: deterministic fallback used in tests and when no API key is configured.
- `OpenAIProvider`: OpenAI-compatible HTTP client with retry/backoff for 429 and 5xx errors.

Prompt assembly:
- System message contains user profile JSON, selected Shared Brain facts, and recent conversation history.
- User message is the current input.
- Only selected context is included; the full graph and full history are never sent.

Fallbacks:
- Graph failure returns empty context and continues.
- LLM failure returns a degraded template response instead of crashing the request.

---

## 6. Error Handling

- Invalid or blank input: HTTP 422 via Pydantic validation.
- Missing profile: not an error; response degrades to general guidance.
- LLM failure: caught and replaced with a fallback message.
- Graph failure: logged and treated as empty memory; API continues.
- Empty memory / no relevant context: allowed; `context_used` reflects only available sources.
- Custom application exceptions map to HTTP status codes: 400, 404, 422, 429, 502, 503.

---

## 7. Project Structure

```
MyNaksh-SumanthKadali/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app and lifespan
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                # Pydantic settings from .env
│   │   ├── exceptions.py            # AppError hierarchy
│   │   └── cache.py                 # TTLCache for LLM responses
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py          # ChatService dependency
│   │   ├── routes.py                # /health, /chat, /users, /brain
│   │   └── schemas.py               # Request/response Pydantic models
│   ├── chat/
│   │   ├── __init__.py
│   │   └── service.py               # Orchestrator pipeline
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                  # Provider protocol
│   │   ├── factory.py               # Provider selection
│   │   ├── mock.py                  # Deterministic test provider
│   │   └── openai.py                # OpenAI-compatible provider
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── extractor.py             # Rule-based + optional LLM fact extraction
│   │   └── short_term.py            # Per-session TTL sliding window
│   ├── brain/
│   │   ├── __init__.py
│   │   ├── factory.py               # Graph store selection
│   │   ├── models.py                # MemoryFact and CandidateFact
│   │   ├── neo4j_store.py           # Neo4j Async driver implementation
│   │   └── store.py                 # GraphStore protocol and in-memory store
│   ├── context/
│   │   ├── __init__.py
│   │   └── selector.py              # Hybrid fact scoring and selection
│   ├── profile/
│   │   ├── __init__.py
│   │   └── models.py                # UserProfile and ProfileUpdate
│   └── astrology/
│       ├── __init__.py
│       └── calculator.py            # Stubbed Sun sign computation
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # Test client and fresh in-memory state
│   └── test_chat.py                 # 10 automated scenarios
├── docker-compose.yml               # Neo4j service
├── requirements.txt                 # Python dependencies
├── .env.example                     # Configuration template
├── .gitignore
└── README.md
```

---

## 8. Environment Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

3. Copy and edit the environment file:

```bash
cp .env.example .env
```

Example `.env`:

```
APP_ENV=development
LOG_LEVEL=INFO
GRAPH_BACKEND=memory
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
LLM_PROVIDER=mock
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=3
CACHE_TTL_SECONDS=300
SHORT_TERM_MAX_MESSAGES=20
SHORT_TERM_TTL_SECONDS=3600
MEMORY_TOP_K=5
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=512
```

- `GRAPH_BACKEND=memory` uses the in-memory graph store. Use this for tests and local development without Neo4j.
- `GRAPH_BACKEND=neo4j` requires a running Neo4j instance.

---

## 9. Running the Server

```bash
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive docs are at `/docs`.

---

## 10. Running Neo4j with Docker

```bash
docker compose up -d neo4j
```

Then set `GRAPH_BACKEND=neo4j` in `.env` and restart the application. Neo4j Browser is available at `http://localhost:7474`.

---

## 11. Running Tests

```bash
python3 -m pytest -q
```

The suite uses the in-memory graph backend and deterministic mock LLM, so no external services or API keys are required. Expected result: 10 passed.

---

## 12. API Reference

### Health

```
GET /health
```

Response:

```json
{ "status": "ok" }
```

### Create or update user profile

```
POST /users
```

Request:

```json
{
  "user_id": "user-123",
  "profile": {
    "name": "Rahul",
    "date_of_birth": "1995-08-15",
    "time_of_birth": "10:30",
    "birth_place": "Delhi",
    "preferred_language": "Hindi",
    "zodiac": "Leo"
  }
}
```

### Chat

```
POST /chat
```

Request:

```json
{
  "user_id": "user-123",
  "session_id": "session-456",
  "message": "What should I focus on for my career?",
  "profile": {
    "date_of_birth": "1995-08-15",
    "birth_place": "Delhi",
    "preferred_language": "Hindi"
  }
}
```

Response:

```json
{
  "response": "Based on your career goals, focus on skill-building, networking, and targeted applications aligned with your transition timeline.",
  "user_id": "user-123",
  "session_id": "session-456",
  "context_used": [ "user_profile", "shared_brain", "conversation_history", "career_goal" ]
}
```

### Get user profile

```
GET /users/{user_id}
```

### Get Shared Brain facts

```
GET /users/{user_id}/brain
```

Response:

```json
{
  "user_id": "user-123",
  "facts": [
    {
      "id": "user-123:goal:career",
      "user_id": "user-123",
      "type": "goal",
      "key": "career",
      "value": "switch jobs next year",
      "relation": "HAS_FACT",
      "confidence": 0.8,
      "source": "conversation",
      "metadata": { "timeframe": "2027" },
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

---

## 13. Step-by-Step Reconstruction Instructions

1. Initialize a Python 3.9+ project directory.
2. Add `requirements.txt` with FastAPI, uvicorn, pydantic, pydantic-settings, httpx, neo4j, pytest, pytest-asyncio, python-dotenv.
3. Add `app/core/config.py` using `pydantic-settings.BaseSettings` with `.env` support.
4. Add `app/core/exceptions.py` with `AppError`, `ValidationError`, `NotFoundError`, `LLMError`, `GraphError`, `RateLimitError`, `UnprocessableError`.
5. Add `app/core/cache.py` with a TTL cache keyed by SHA-256 of request components.
6. Add `app/profile/models.py` with `UserProfile` and `ProfileUpdate`.
7. Add `app/astrology/calculator.py` with a stubbed `compute_zodiac` from date of birth.
8. Add `app/brain/models.py` with `MemoryFact` and `CandidateFact`.
9. Define `GraphStore` protocol in `app/brain/store.py` and implement `InMemoryGraphStore` with async locking, fact upsert keyed by `(type, key)`, retrieval, search, delete, and clear.
10. Add `app/brain/neo4j_store.py` with the Neo4j async driver implementing the same protocol using `User` and `Fact` nodes and `HAS_FACT` relationships.
11. Add `app/brain/factory.py` to select memory or Neo4j based on `GRAPH_BACKEND`.
12. Add `app/memory/short_term.py` with a per-session deque sliding window and TTL eviction.
13. Add `app/memory/extractor.py` with rule-based profile/goal/interest/preference extraction and an optional LLM hybrid extractor.
14. Add `app/context/selector.py` to score and select top-K facts and build `context_used` tags.
15. Add `app/llm/base.py`, `app/llm/mock.py`, `app/llm/openai.py`, and `app/llm/factory.py` for pluggable LLM generation with retry and fallback.
16. Add `app/chat/service.py` to orchestrate validation, profile upsert, short-term append, fact extraction, memory upsert, context selection, cached LLM generation, assistant append, and response assembly.
17. Add `app/api/schemas.py`, `app/api/dependencies.py`, and `app/api/routes.py` for `/health`, `/chat`, `/users`, `/users/{user_id}`, and `/users/{user_id}/brain`.
18. Add `app/main.py` with FastAPI lifespan that starts and shuts down the `ChatService`.
19. Add `tests/conftest.py` and `tests/test_chat.py` covering new user, memory creation, retrieval, follow-up, new-session persistence, irrelevant memory filtering, correction, missing profile, user creation, and health.
20. Run `python3 -m pytest -q` and `uvicorn app.main:app --reload`.

---

## 14. Evaluation Approach

Shared Brain quality can be evaluated by replaying scripted conversations and checking:

- Memory accuracy: extracted facts match stated user information.
- Context relevance: selected facts overlap with query intent.
- Personalization: responses reference stored goals, profile, or zodiac attributes.
- Conversation consistency: follow-up answers align with prior turns.
- Irrelevant context suppression: unrelated facts are not injected into unrelated queries.
- Memory persistence: facts survive across sessions and service restarts when using Neo4j.

A sophisticated evaluation framework is not required; the provided 10 pytest scenarios cover the core behavior.

---

## 15. Configuration Reference

| Variable | Default | Description |
|---|---|---|
| APP_ENV | development | Deployment environment |
| LOG_LEVEL | INFO | Logging level |
| GRAPH_BACKEND | memory | memory or neo4j |
| NEO4J_URI | bolt://localhost:7687 | Neo4j connection URI |
| NEO4J_USER | neo4j | Neo4j username |
| NEO4J_PASSWORD | password | Neo4j password |
| LLM_PROVIDER | mock | mock or openai |
| OPENAI_API_KEY | | OpenAI API key |
| OPENAI_BASE_URL | https://api.openai.com/v1 | OpenAI-compatible base URL |
| OPENAI_MODEL | gpt-4o-mini | LLM model name |
| LLM_TIMEOUT_SECONDS | 30 | LLM request timeout |
| LLM_MAX_RETRIES | 3 | LLM retry count |
| CACHE_TTL_SECONDS | 300 | LLM response cache TTL |
| SHORT_TERM_MAX_MESSAGES | 20 | Short-term window size |
| SHORT_TERM_TTL_SECONDS | 3600 | Short-term session TTL |
| MEMORY_TOP_K | 5 | Max facts sent to LLM |
| LLM_TEMPERATURE | 0.7 | LLM temperature |
| LLM_MAX_TOKENS | 512 | LLM max tokens |
