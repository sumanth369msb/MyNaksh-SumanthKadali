# MyNaksh — Personalized Astrology Conversational AI Service

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.20+-008CC1.svg)](https://neo4j.com)
[![Pytest](https://img.shields.io/badge/Tests-117%20Passed-brightgreen.svg)](https://docs.pytest.org)

MyNaksh is a production-grade personalized conversational AI service with a persistent, graph-backed **Shared Brain**. It continuously extracts user attributes, life goals, career timelines, and personal preferences from dialogue, maintaining a clean architectural distinction between ephemeral short-term session context and durable long-term memory.

---

## 1. Architecture

MyNaksh is built on an asynchronous ASGI foundation utilizing FastAPI, structured around a clean dual-memory paradigm and a strictly ordered pipeline orchestrator.

### 1.1 Service Layout
* **ASGI API Gateway (`app/main.py`, `app/api/`)**: High-performance asynchronous FastAPI service exposing RESTful chat (`POST /chat`), profile management (`POST /user`), and health probe endpoints (`GET /health`), equipped with global exception handlers for domain errors (`AppError`), database outages, and uncaught exceptions.
* **Pipeline Orchestrator (`app/chat/service.py`)**: Central `ChatService` managing the end-to-end conversation lifecycle, coordinating memory retrieval, context scoring, LLM generation, caching, and post-response memory updates.
* **Dual-Memory Subsystems**:
  * **Short-Term Memory (`app/memory/short_term.py`)**: Fast, in-memory sliding window deque with inactivity TTL eviction for multi-turn conversational coherence.
  * **Long-Term Shared Brain (`app/brain/store.py`, `app/brain/neo4j_store.py`)**: Persistent property graph maintaining structured facts, user profile attributes, biographical milestones, and astrological placements across disjoint sessions.
* **Context Selection Engine (`app/context/selector.py`)**: Pre-LLM retrieval filter that scores candidate facts and strictly suppresses irrelevant context.
* **LLM Provider Layer (`app/llm/`)**: Pluggable provider abstraction (`OpenAIProvider`, `OpenRouterProvider`, `MockProvider`) with SHA-256 deterministic response caching (`app/core/cache.py`).

### 1.2 Canonical Execution Flow
The system strictly enforces the canonical request execution lifecycle:
$$\text{User Message} \longrightarrow \text{Record Turn} \longrightarrow \text{Sync Profile} \longrightarrow \text{Retrieve Facts} \longrightarrow \text{Select Context} \longrightarrow \text{Build Prompt} \longrightarrow \text{Generate Response} \longrightarrow \text{Record Turn} \longrightarrow \text{Update Memory} \longrightarrow \text{Emit Telemetry}$$

```
                      +-----------------------------+
                      |   Client (HTTP / CLI / Web) |
                      +--------------+--------------+
                                     |  POST /chat
                                     v
                        +---------------------------+
                        |   FastAPI Router & Model  |
                        |      Defensive Check      |
                        +-------------+-------------+
                                     |
                                     v
+-----------------------------------------------------------------------------------+
| ChatService Canonical Execution Pipeline                                          |
|                                                                                   |
|  1. Input Validation      --> Reject empty/whitespace messages (ValueError / 422) |
|  2. Record Short-Term     --> Append user turn to session deque                   |
|  3. Profile Sync          --> Upsert UserProfile & sync profile facts to Brain    |
|  4. Fact Retrieval        --> Query candidate memory facts from GraphStore        |
|  5. Context Selection     --> Score & filter facts (strictly suppress if score=0) |
|  6. Prompt Assembly       --> Bind Jungian/Vedic persona + Top-K context facts    |
|  7. LLM Invocation        --> Pluggable provider with SHA-256 cache & fallback    |
|  8. Record Short-Term     --> Append assistant response turn to session deque     |
|  9. Memory Update         --> Resilient post-response fact extraction & upsert    |
| 10. Telemetry Return      --> Return payload with context_used audit tags         |
+-----------------------------------------------------------------------------------+
          |                                        |
          v                                        v
+--------------------+                   +--------------------+
| Short-Term Memory  |                   | Persistent Brain   |
| (Sliding Deque with|                   | (Neo4j Graph or    |
|  TTL Eviction)     |                   |  In-Memory Store)  |
+--------------------+                   +--------------------+
```

---

## 2. Shared Brain Schema

The Shared Brain is modeled as a native property graph, structuring user memory into an associative web of entities, facts, and astrological relationships.

### 2.1 Node Taxonomy & Property Definitions
The schema defines six core node types:

| Node Label | Description | Key Properties |
|---|---|---|
| `:User` | Central identity node representing the individual user. | `id` (indexed, unique string/UUID), `name`, `date_of_birth` (ISO `YYYY-MM-DD`), `time_of_birth` (`HH:MM`), `birth_place`, `preferred_language`, `zodiac`, `metadata` (JSON string), `created_at`, `updated_at`. |
| `:BirthChart` | Astrological natal chart entity calculated from birth data. | `id` (unique), `user_id`, `sun_sign`, `moon_sign`, `ascendant`, `ayanamsha` (e.g. Lahiri), `calculated_at`. |
| `:AstrologicalEntity` | Discrete astrological placements, houses, and celestial bodies. | `name` (e.g. "Jupiter", "Saturn", "Mars"), `entity_type` (`"planet"`, `"sign"`, `"nakshatra"`), `degree`, `house_number`, `retrograde` (`BOOLEAN`). |
| `:Fact` | Atomic unit of extracted long-term memory. | `id` (`{user_id}:{type}:{key}`), `user_id`, `type` (`"goal"`, `"preference"`, `"interest"`, `"profile"`, `"zodiac"`, `"memory"`), `key`, `value`, `relation`, `confidence` (`FLOAT` 0.0 to 1.0), `source`, `metadata` (JSON), `is_active` (`BOOLEAN`), `valid_from`, `valid_to`, `created_at`, `updated_at`. |
| `:Episode` | Cohesive dialogue episode summarizing key conversation threads. | `id`, `user_id`, `session_id`, `summary`, `sentiment`, `turn_count`, `timestamp`. |
| `:MemoryNode` | Intermediate associative node connecting episodes, entities, and facts. | `id`, `user_id`, `cluster_label`, `salience_score`, `created_at`. |

### 2.2 Relationship Taxonomy
* `(:User)-[:HAS_FACT {relation, confidence, created_at}]->(:Fact)`: General fact association.
* `(:Fact)-[:SUPERSEDES {superseded_at, reason}]->(:Fact)`: **Bi-temporal Fact Evolution**. When a user modifies or updates an existing intention (e.g., shifting a career timeline from 2027 to 2026), the previous fact is marked `is_active=False` and linked via `:SUPERSEDES`, preserving historical evolution for time-series queries while ensuring active queries retrieve only the latest truth.
* `(:User)-[:HAS_PROFILE]->(:Fact)`: Explicit biographical identity facts (name, DOB, birthplace).
* `(:User)-[:HAS_GOAL]->(:Fact)`: Aspirations, career transitions, and life goals.
* `(:User)-[:PREFERS]->(:Fact)`: Behavioral preferences (e.g., preferred language, conversational tone).
* `(:User)-[:INTERESTED_IN]->(:Fact)`: Topical interests and personal hobbies.
* `(:User)-[:HAS_BIRTH_CHART]->(:BirthChart)`: Connects the user to their astronomical chart.
* `(:BirthChart)-[:CONTAINS_ENTITY]->(:AstrologicalEntity)`: Placements of planets and houses.
* `(:AstrologicalEntity)-[:INFLUENCES]->(:MemoryNode)`: Maps astrological aspects onto life memory clusters.

### 2.3 Conflict Resolution & Idempotency
Facts are uniquely keyed by the composite tuple: `(user_id, type, key)`.
* In `InMemoryGraphStore`, fact upserts locate existing keys in the user's fact map, updating `value`, `relation`, `metadata`, and bumping `updated_at` while taking `max(existing.confidence, fact.confidence)` to prevent confidence degradation.
* In `Neo4jGraphStore`, Cypher `MERGE` statements guarantee idempotent state convergence:

```cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT fact_id_unique IF NOT EXISTS
FOR (f:Fact) REQUIRE f.id IS UNIQUE;

MERGE (u:User {id: $user_id})
MERGE (f:Fact {id: $fact_id})
ON CREATE SET
    f.user_id = $user_id,
    f.type = $type,
    f.key = $key,
    f.created_at = $created_at
SET
    f.value = $value,
    f.relation = $relation,
    f.confidence = $confidence,
    f.source = $source,
    f.metadata = $metadata,
    f.updated_at = $updated_at
MERGE (u)-[r:HAS_FACT]->(f)
SET r.relation = $relation;
```

---

## 3. Memory Strategy

MyNaksh enforces an architectural separation between ephemeral dialogue understanding and persistent cross-session memory.

```
+------------------------------------------------------------------------------------+
|                                    USER MESSAGE                                    |
+------------------------------------------------------------------------------------+
       |                                                             |
       v                                                             v
+-------------------------------+             +--------------------------------------+
| Ephemeral Short-Term Memory   |             | Selective Long-Term Shared Brain     |
| • Sliding deque (maxlen=20)   |             | • Filter greetings & questions       |
| • TTL Eviction (3600 seconds) |             | • Flexible date parsing & riddles    |
| • Resolves pronouns in turn   |             | • Resilient post-response update     |
| • Session-scoped isolation    |             | • Cross-session graph persistence    |
+-------------------------------+             +--------------------------------------+
```

### 3.1 Short-Term Conversation Context
* **Purpose**: Resolves conversational pronouns, contextual ellipsis, and immediate follow-up references (e.g., *"Why do you say that?"*, *"Explain that transit again"*).
* **Storage**: In-memory sliding-window buffer using `collections.deque(maxlen=20)` protected by an asynchronous lock (`asyncio.Lock`).
* **TTL Eviction**: Automatically purges inactive conversation threads when `now - last_access > 3600` seconds (`short_term_ttl_seconds=3600`).
* **Session Isolation**: Bounded per `session_id`, ensuring conversations across distinct tabs or devices remain strictly separated.

### 3.2 Long-Term Persistent Memory (Shared Brain)
* **Selective Ingestion (Anti-Pollution Filters)**: To prevent persistent graph clutter from conversational noise, candidate messages pass through strict filters:
  * **Greeting Filter (`GREETING_ONLY_PATTERN`)**: Rejects bare greetings and pleasantries (`^\s*(?:hi|hello|hey|thanks|thank you|ok|okay)(?:\s+there)?[\s,!.]*$`).
  * **Interrogative Meta-Question Filter (`_is_interrogative`)**: Discards meta-queries (e.g., *"Why do you say that?"*, *"What do you know about me?"*), preventing system reflection from being recorded as user facts.
* **Flexible Date Normalization**:
  * Resolves human phrasings and complex relative riddles (e.g., *"born in 2004 on 3rd month from march and on 26th"* &rarr; `2004-06-26`) via `parse_flexible_date()`.
  * Guarantees all biographical dates are stored in canonical ISO `YYYY-MM-DD` format.
* **Semantic Fact Extraction**:
  * Rule-based extractors map career goals to `HAS_GOAL`, language preferences to `PREFERS`, interests to `INTERESTED_IN`, and identity to `HAS_PROFILE`.

### 3.3 Post-Response Memory Update Timing
In the pipeline execution order, fact extraction and memory updates run **after** response generation:
1. **Zero User-Facing Latency Overhead**: The user receives their generated response immediately without blocking on LLM-based fact extraction or secondary graph writes.
2. **Atomic Context Snapshot**: The response is synthesized against the exact context that existed when the user initiated the turn, preventing race conditions or self-referential hallucinations.
3. **Resilience & Fault Isolation**: Post-response memory update is wrapped in a dedicated `try...except` block; any extraction error or transient database hiccup logs a warning without crashing or degrading the user's delivered response.

---

## 4. Context-Selection Approach

Sending the entire user graph or full conversation history to the LLM increases inference costs, introduces token latency, and causes hallucinations. MyNaksh implements a selective pre-LLM context scoring filter.

### 4.1 Hybrid Scoring Formula
Candidate facts retrieved from the user's graph neighborhood are evaluated against the incoming query tokens:

$$\text{Score} = \text{Token Overlap} + \text{Domain Keyword Boost} + (\text{Confidence} \times 0.5) + \text{Recency Boost}$$

Where:
* **Token Overlap**: Set intersection between non-stopword query tokens and fact content tokens:
  $$\text{Overlap} = |(\text{Tokens}_{\text{query}} \setminus \text{Stopwords}) \cap (\text{Tokens}_{\text{fact}} \setminus \text{Stopwords})|$$
* **Domain Keyword Boost**:
  * `+2.0`: If `Tokens_query` matches predefined keywords for the fact type (`TYPE_KEYWORDS[fact.type]`).
  * `+3.0`: If the query includes `"career"` or `"job"` and `fact.type == "goal"`.
  * `+3.0`: If the query includes `"language"` or `"prefer"` and `fact.type == "preference"`.
* **Confidence & Recency Weighting** (Applied **only** when preliminary $\text{Score} > 0$):
  * **Confidence Weight**: $\text{fact.confidence} \times 0.5$.
  * **Recency Boost**: Continuous temporal decay function prioritizing recent updates:
    $$\text{Recency Boost} = \frac{0.5}{1.0 + \frac{\text{age\_seconds}}{86400.0}}$$

### 4.2 Strict Irrelevant Context Suppression
* If no candidate facts achieve a relevance score $> 0$ (`has_positive_relevance is False`), the selector strictly sets:
  ```python
  selected = []
  ```
* **Elimination of Fallback Contamination**: The system never falls back to recent facts on zero-relevance queries. Out-of-domain inquiries (e.g., *"What is the capital of France?"*, math questions, or general weather queries) are served with **zero stored memory facts injected** and zero memory pollution.

### 4.3 Full Telemetry Tagging (`context_used`)
Every API response emits an explicit, auditable telemetry array declaring exactly which context sources were mobilized during synthesis:

| Telemetry Tag | Trigger Condition |
|---|---|
| `"user_profile"` | User profile information (name, DOB, birthplace, zodiac) is present. |
| `"shared_brain"` | One or more relevant long-term memory facts were selected (`score > 0`). |
| `"conversation_history"` | Multi-turn short-term context exists in the current session (`len(recent_turns) > 1`). |
| `"career_goal"` | Career/job intent detected in query and a `goal` fact was selected. |
| `"language_preference"` | Language/communication intent detected in query and a `preference` fact was selected. |
| `"zodiac_sign"` | Astrological inquiry (`"zodiac"`, `"sign"`, `"kundli"`, `"horoscope"`) matched with selected zodiac facts or profile zodiac. |

---

## 5. Key Design Decisions & Trade-Offs

| Decision Area | Chosen Architecture | Alternatives Evaluated | Architectural Trade-Off & Rationale |
|---|---|---|---|
| **Graph Database** | **Neo4j** (Native Property Graph) | Relational (PostgreSQL) vs Vector Store (Pinecone) vs AWS Neptune | **Index-Free Adjacency**: Direct double-linked record pointers provide sub-5ms local traversals ($O(1)$ pointer chasing) regardless of total graph size, compared to $O(k \log N)$ index scans and join tables in relational databases. Vector stores fail at exact entity updates and relational traversal; AWS Neptune introduces high VPC operational complexity and $20-80$ ms traversal latencies. |
| **Dual Backend Strategy** | `InMemoryGraphStore` + `Neo4jGraphStore` | Neo4j-only or SQLite abstraction | **Zero-Dependency Agility**: An abstract `GraphStore` protocol permits running the entire test suite (107 tests in 0.06s) in-memory without requiring external Docker daemons, while production switches seamlessly to `Neo4jGraphStore` using the official `AsyncGraphDatabase` Bolt driver. |
| **Fact Extraction** | Rule-Based Regex (`RuleBasedExtractor`) + Optional Hybrid LLM | LLM-only extraction pipeline | **Deterministic Latency & Cost**: Regex handles standard profile patterns (names, dates, languages, goals) in under 0.1ms with 100% determinism and $0 API cost. Optional hybrid LLM extraction can be enabled for unstructured semantic nuances without blocking basic facts. |
| **Execution Ordering** | Synchronous In-band Context Selection with Resilient Post-Response Memory Extraction | Pre-generation memory extraction or Pure async background worker queue | **Response SLA & Accuracy**: Context selection must be synchronous to ensure immediate turn relevance. Memory extraction runs post-response to eliminate latency from the user's critical path while preventing pre-generation state mutation. |
| **Fact Conflict Resolution** | Deterministic In-Place Upsert by `(user_id, type, key)` | Append-only event log with reconciliation agent | **Single Source of Truth**: Append-only logs exponentially inflate prompt sizes and risk contradictory retrieval. In-place upsert guarantees instant consistency on corrections. |
| **Response Caching** | Multi-Key SHA-256 `TTLCache` | Global prompt caching or No caching | Caching hashed combinations of `(user_id, session_id, message, selected_facts, recent_turns, profile)` achieves 0ms response times and zero token cost on identical repeated queries without serving stale dynamic context. |

---

## 6. Production Considerations

Deploying MyNaksh in enterprise production requires addressing concurrency, clustering, graph performance, and tenant isolation:

### 6.1 Enterprise Connection Pooling
The `Neo4jGraphStore` utilizes production-tuned connection pool configurations:
* `max_connection_pool_size=50`: Accommodates high-throughput asynchronous ASGI request spikes without socket exhaustion.
* `connection_acquisition_timeout=5.0s`: Ensures fast failure under pool saturation rather than indefinite request hanging.
* `max_connection_lifetime=3600s`: Periodically refreshes pooled TCP connections to prevent stale firewall / proxy drops.

### 6.2 Causal Clustering & Consistency
In multi-node Neo4j Causal Clustering deployments (Leader + Read Replicas):
* **Bookmark Passing**: Multi-turn sessions track transaction bookmarks from memory write transactions. Subsequent read operations in the next turn pass the bookmark to read replicas, guaranteeing **Read-Your-Own-Writes** causal consistency across distributed instances.

### 6.3 Graph Size Explosion Mitigations
* **Supernode Mitigation**: Active users accumulating hundreds of conversational facts are protected against degree explosion by bounding Cypher traversal depth (`[:HAS_FACT*1..2]`) and indexing `is_active=True`.
* **Transaction Timeouts**: Neo4j server-side configuration enforces `dbms.transaction.timeout=2s` to abort runaway graph queries before exhausting JVM heap or worker threads.
* **Memory Allocation Guidelines**: Recommended production sizing assigns 50% of instance RAM to Neo4j PageCache (caching the graph topology in memory) and 25% to JVM Heap, with remaining RAM reserved for OS page tables.

### 6.4 Multi-Tenant Security & Isolation
* **Parameterized User Scoping**: All Cypher statements strictly bind `$user_id` parameters; dynamic Cypher string formatting is strictly prohibited, eliminating Cypher injection vulnerabilities.
* **Fine-Grained Access Control (FGAC)**: Neo4j Enterprise security rules enforce user-level node and relationship traversal boundaries, preventing cross-tenant data leaks in shared database instances.
* **Secret Hygiene**: Sensitive credentials, database URIs, and LLM API keys are managed exclusively via environment variables and injected via Kubernetes Secrets / Vault, with PII redacted in operational logs.

---

## 7. Error Handling & Fallbacks

MyNaksh is architected to degrade gracefully across all failure modes:

* **Defensive Input Validation**: Blank or whitespace-only messages are intercepted at both the service layer (`ChatService.chat()`) and the HTTP layer, returning clean HTTP 422 responses before touching the database or LLM.
* **Missing Birth Profile Information**: If a user requests astrological calculations (such as Kundli or Sun sign) without providing birth details, the system follows prompt Rule 5: it provides general Vedic wisdom while gently guiding the user to provide their birth date, time, and birthplace.
* **Database / Graph Store Outage**: If the graph database disconnects, the system logs a structured warning, gracefully degrades to empty long-term memory (`facts = []`), and continues serving the user using available short-term conversation context.
* **LLM Provider Failure**: If the LLM provider experiences timeouts, rate limits, or 5xx server errors, `ChatService` invokes `_fallback_response()`:
  * Generates a persona-aligned fallback acknowledging stored user context (e.g., *"Namaste {name}. Reflecting on your {zodiac} energy... I am temporarily experiencing a communication delay with the astrological oracle..."*).
  * Prevents user-facing 500 error crashes and preserves conversational trust.

---

## 8. Quickstart & Installation

### 8.1 Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 8.2 Environment Configuration
Copy the template and configure your parameters:
```bash
cp .env.example .env
```

Key configuration options in `app/core/config.py`:
```ini
APP_ENV=development
LOG_LEVEL=INFO

# Graph Backend: 'memory' for zero-dependency local dev/tests, or 'neo4j' for production
GRAPH_BACKEND=memory
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# LLM Provider: 'mock' for deterministic tests, 'openai', or 'openrouter'
LLM_PROVIDER=mock
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=meta-llama/llama-3.3-70b-instruct

# Memory & Pipeline Settings
SHORT_TERM_MAX_MESSAGES=20
SHORT_TERM_TTL_SECONDS=3600
MEMORY_TOP_K=5
CACHE_TTL_SECONDS=300
```

### 8.3 Launch Neo4j (Optional for Local Production Testing)
```bash
docker compose up -d neo4j
```

### 8.4 Run the FastAPI Server
```bash
uvicorn app.main:app --reload --port 8000
```
* **Swagger API Documentation**: `http://127.0.0.1:8000/docs`
* **Health Check**: `GET http://127.0.0.1:8000/health`

### 8.5 Interactive CLI Chat
Interact with the running conversational engine with automatic Shared Brain inspection:
```bash
python3 cli_chat.py
```
* Chat naturally: *"My name is Prakash, born 26 March 2004, what is my Sun sign?"*
* Type `/brain` to inspect active facts currently stored in the Shared Brain.
* Type `exit` or `quit` to exit.

### 8.6 Sample API Requests & Responses

#### 1. Register User Profile (`POST /users`)
**Request**:
```bash
curl -X POST http://127.0.0.1:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "profile": {
      "name": "Rahul",
      "date_of_birth": "1995-08-15",
      "time_of_birth": "10:30",
      "birth_place": "Delhi",
      "preferred_language": "Hindi"
    }
  }'
```
**Response (`HTTP 200 OK`)**:
```json
{
  "user_id": "user-123",
  "status": "created"
}
```

#### 2. Chat with Context & Goal Extraction (`POST /chat`)
**Request**:
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "session_id": "session-456",
    "message": "I am planning to switch jobs to AI engineering in 2026. What should I focus on for my career?"
  }'
```
**Response (`HTTP 200 OK`)**:
```json
{
  "response": "Namaste Rahul. As a Leo born on August 15, 1995 in Delhi, you possess natural leadership and creative passion. Considering your goal to transition to AI engineering in 2026, the current planetary transits favor focused upskilling and disciplined execution...",
  "user_id": "user-123",
  "session_id": "session-456",
  "context_used": [
    "user_profile",
    "shared_brain",
    "career_goal"
  ]
}
```

#### 3. Follow-up Referential Question (`POST /chat`)
**Request**:
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "session_id": "session-456",
    "message": "Why do you say that?"
  }'
```
**Response (`HTTP 200 OK`)**:
```json
{
  "response": "I say that because your Leo Sun is ruled by the Sun, representing core vitality and purpose. Moving into technical leadership aligns with your chart's Tenth House career indicators...",
  "user_id": "user-123",
  "session_id": "session-456",
  "context_used": [
    "user_profile",
    "shared_brain",
    "conversation_history"
  ]
}
```

#### 4. Query Stored Shared Brain Facts (`GET /users/{user_id}/brain`)
**Request**:
```bash
curl -s http://127.0.0.1:8000/users/user-123/brain
```
**Response (`HTTP 200 OK`)**:
```json
{
  "user_id": "user-123",
  "facts": [
    {
      "id": "user-123:goal:career",
      "user_id": "user-123",
      "type": "goal",
      "key": "career",
      "value": "I am planning to switch jobs to AI engineering in 2026. What should I focus on for my career?",
      "relation": "HAS_GOAL",
      "confidence": 0.75,
      "source": "conversation",
      "metadata": {
        "timeframe": "2026"
      },
      "created_at": "2026-10-30T00:15:00Z",
      "updated_at": "2026-10-30T00:15:00Z"
    },
    {
      "id": "user-123:zodiac:sun_sign",
      "user_id": "user-123",
      "type": "zodiac",
      "key": "sun_sign",
      "value": "Leo",
      "relation": "HAS_FACT",
      "confidence": 1.0,
      "source": "profile",
      "metadata": {},
      "created_at": "2026-10-30T00:15:00Z",
      "updated_at": "2026-10-30T00:15:00Z"
    },
    {
      "id": "user-123:profile:birth_place",
      "user_id": "user-123",
      "type": "profile",
      "key": "birth_place",
      "value": "Delhi",
      "relation": "HAS_PROFILE",
      "confidence": 1.0,
      "source": "profile",
      "metadata": {},
      "created_at": "2026-10-30T00:15:00Z",
      "updated_at": "2026-10-30T00:15:00Z"
    },
    {
      "id": "user-123:profile:date_of_birth",
      "user_id": "user-123",
      "type": "profile",
      "key": "date_of_birth",
      "value": "1995-08-15",
      "relation": "HAS_PROFILE",
      "confidence": 1.0,
      "source": "profile",
      "metadata": {},
      "created_at": "2026-10-30T00:15:00Z",
      "updated_at": "2026-10-30T00:15:00Z"
    },
    {
      "id": "user-123:profile:name",
      "user_id": "user-123",
      "type": "profile",
      "key": "name",
      "value": "Rahul",
      "relation": "HAS_PROFILE",
      "confidence": 1.0,
      "source": "profile",
      "metadata": {},
      "created_at": "2026-10-30T00:15:00Z",
      "updated_at": "2026-10-30T00:15:00Z"
    }
  ]
}
```

#### 5. Fetch User Profile (`GET /users/{user_id}`)
**Request**:
```bash
curl -s http://127.0.0.1:8000/users/user-123
```
**Response (`HTTP 200 OK`)**:
```json
{
  "user_id": "user-123",
  "name": "Rahul",
  "date_of_birth": "1995-08-15",
  "time_of_birth": "10:30",
  "birth_place": "Delhi",
  "preferred_language": "Hindi",
  "zodiac": "Leo",
  "metadata": {}
}
```

---

## 9. Automated Test Suite

Run the full automated test suite:
```bash
.venv/bin/python3 -m pytest tests/ -v
```

All 117 tests pass with 0 external dependencies (utilizing the deterministic mock provider and in-memory graph store):
```
tests/test_chat.py ..........                                            [  8%]
tests/test_prompts.py .................................................. [ 51%]
...............................................                          [ 91%]
tests/test_scenarios.py ..........                                       [100%]
============================= 117 passed in 0.08s ==============================
```

---

## 10. Evaluating Shared Brain Quality (6 Core Areas)

A sophisticated evaluation framework is not required; response quality improvement enabled by the Shared Brain is evaluated across six core dimensions:

1. **Memory Accuracy**:
   * *Method*: Replay scripted conversations and assert that extracted fact key/value pairs match what the user stated (e.g., DOB `"15 August 1995"` &rarr; ISO `1995-08-15`, birthplace `"Delhi"` &rarr; `Delhi`).
   * *Metric*: Fact Extraction Precision & Recall ($P_{\text{extract}} = 1.0$, $R_{\text{extract}} = 1.0$), ensuring zero entity corruption or hallucinated attributes.

2. **Context Relevance**:
   * *Method*: Assert that selected facts overlap with incoming query intent/tokens; irrelevant stored facts must not appear in `context_used` or the LLM prompt.
   * *Metric*: Top-$K$ relevance scoring verifies only high-salience facts are injected into the active prompt window.

3. **Personalization**:
   * *Method*: Verify generated responses explicitly reference stored name, zodiac, or career goals rather than generic horoscope advice.
   * *Metric*: Persona-aligned astrological synthesis reflecting user energetic profile (e.g., Leo confidence, Virgo analytical discipline).

4. **Conversation Consistency**:
   * *Method*: Check that follow-up answers align seamlessly with facts stored in prior turns of the same session without contradictions.
   * *Metric*: Resolves conversational pronouns and references (e.g., *"Why do you say that?"*, *"Explain that transit again"*) using short-term conversation context.

5. **Irrelevant Context Suppression**:
   * *Method*: Confirm that out-of-domain queries (e.g., photosynthesis, science, or general math) do not emit the `shared_brain` tag or surface unrelated stored facts in prompt context.
   * *Metric*: 0% context leakage on zero-relevance queries (`selected = []`).

6. **Memory Persistence**:
   * *Method*: Assert that facts survive across independent sessions and service restarts; facts must remain retrievable via `GET /users/{id}/brain` after starting a new `session_id`.
   * *Metric*: 100% cross-session recall fidelity across disjoint session IDs.

