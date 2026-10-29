# Engineering Guide: Coding, Debugging & Error Remediation — MyNaksh

This guide documents proven patterns, debugging workflows, and error remediation procedures specifically tailored to the `MyNaksh-SumanthKadali` codebase. Use this document as persistent memory when developing, modifying, or troubleshooting.

---

## 1. How to Properly Write Code in This Repository

### 1.1 Python Standard & Compatibility
- **Target Runtime**: Python 3.9+ standard library.
- **Imports**: Use `from __future__ import annotations` at the top of every module that uses modern typing syntax (`int | None`).
- **Protocols & Type Safety**:
  - Whenever defining a `typing.Protocol` (such as `GraphStore` or `LLMProvider`), ALWAYS decorate it with `@typing.runtime_checkable`.
  - Without `@runtime_checkable`, any call to `isinstance(instance, ProtocolClass)` raises a `TypeError`.

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable

@runtime_checkable
class GraphStore(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    ...
```

### 1.2 Pydantic v2 Best Practices
- Use `pydantic.BaseModel` with field definitions (`Field(...)`, `Field(default_factory=dict)`).
- For validators, use `@field_validator("field_name")` with `@classmethod` decorator.
- For serialization, use `.model_dump(mode="json", exclude_none=True)` or `.model_dump_json()`. Avoid deprecated `.dict()` or `.json()`.

### 1.3 Asynchronous Concurrency & In-Memory Stores
- Every store operation in `InMemoryGraphStore` and `ShortTermMemory` must acquire an `asyncio.Lock` when modifying shared dictionaries (`self._users`, `self._facts`, `self._sessions`).
- Lazy-initialize locks (`_lock: asyncio.Lock | None = None`) to avoid attaching locks to an event loop that might be destroyed between pytest runs.

---

## 2. How to Fix Code & Maintain Existing Functionality

### 2.1 The Non-Breaking Invariant
Before modifying any line of code in `app/`:
1. Run the existing test suite:
   ```bash
   .venv/bin/python3 -m pytest -v
   ```
2. Verify all existing tests pass (currently 22 passed, 1 skipped).
3. Any fix MUST preserve existing contracts and behavior:
   - Status codes must remain identical (e.g. 422 for blank messages, 200 for chat, 404 for missing users).
   - Response structures must strictly adhere to `ChatResponse`, `CreateUserRequest`, etc.

### 2.2 Surgical Edit Principles
- Change only the lines required to fix the specific defect.
- Do not refactor unrelated methods or rewrite functional classes.
- Ensure all variable names and function signatures match the existing convention (`user_id`, `session_id`, `fact_id`, `context_used`).

---

## 3. How to Fix Common Errors & Known Pitfalls in This Codebase

### 3.1 Regular Expression Extraction Pitfalls
**Defect 1: Greeting Prefix Dropping All Facts**
- *Problem*: Messages starting with "Hi", "Hello", "Hey" (e.g., `"Hello, my name is Rahul"`) match `IGNORE_PATTERNS` at line 29 of `extractor.py`, causing `extract()` to return `[]`.
- *Fix*: Only ignore the message if the entire message is solely a greeting or pleasantry without trailing content, OR strip leading greeting phrases before applying durable fact extractors.

**Defect 2: Verb/Adjective Collisions in Name Matching**
- *Problem*: `re.search(r"(?:my name is|i am|i'm)\s+([A-Za-z][A-Za-z\-']*)", clean, re.I)` causes `"I am planning to switch jobs"` to extract `name = "planning"`, or `"I am confused"` to extract `name = "confused"`.
- *Fix*:
  - Disallow common verbs/adjectives following "I am" / "I'm" (`planning`, `looking`, `confused`, `trying`, `born`, `hoping`, `ready`, `happy`).
  - Require the extracted name to begin with an uppercase letter (`[A-Z][a-z]+`) unless preceded by explicit `"my name is"`.

**Defect 3: Language Preference String Extraction**
- *Problem*: `"My preferred language is English"` extracts `language = "is"`. `"I prefer to speak Hindi"` fails to match.
- *Fix*: Match against known language tokens (e.g., `hindi`, `english`, `tamil`, `telugu`, `spanish`, `french`, etc.) or capture the substantive noun following `"preferred language is <word>"` or `"prefer <word>"`.

### 3.2 Cypher Query Syntax Hazards in Neo4j
**Defect: Clause Ordering for `ON CREATE SET`**
- *Problem*:
  ```cypher
  MERGE (f:Fact {id: $fact_id})
  SET f.type = $type ...
  ON CREATE SET f.created_at = $created_at
  ```
  In Neo4j Cypher, `ON CREATE SET` and `ON MATCH SET` MUST immediately follow `MERGE`. Putting a regular `SET` between `MERGE` and `ON CREATE` produces a syntax parse error: `Invalid input 'ON'`.
- *Fix*:
  ```cypher
  MERGE (u:User {id: $user_id})
  MERGE (f:Fact {id: $fact_id})
  ON CREATE SET f.created_at = $created_at
  SET f.type = $type,
      f.key = $key,
      f.value = $value,
      f.relation = $relation,
      f.confidence = $confidence,
      f.source = $source,
      f.metadata = $metadata,
      f.updated_at = $updated_at
  MERGE (u)-[:HAS_FACT]->(f)
  ```

**Defect: Orphan Facts on `clear_user`**
- *Problem*: `MATCH (u:User {id: $uid}) DETACH DELETE u` deletes the User and relationship, leaving orphan `Fact` nodes in the database.
- *Fix*:
  ```cypher
  MATCH (u:User {id: $uid})
  OPTIONAL MATCH (u)-[:HAS_FACT]->(f:Fact)
  DETACH DELETE u, f
  ```

### 3.3 Context Selector Scoring & Tag Hazards
**Defect 1: Unconditional Confidence Boosts**
- *Problem*: Adding `score += fact.confidence * 0.5` unconditionally means every fact gets `score >= 0.4`, so completely irrelevant facts pass `score > 0` and are falsely labeled as relevant.
- *Fix*: Calculate query overlap + keyword boost. Only if `score > 0` do you add `fact.confidence * 0.5`.

**Defect 2: Missing `language_preference` Tag**
- *Problem*: The specification specifies `language_preference` as a valid tag, but `ContextSelector` never appends it.
- *Fix*: Append `"language_preference"` when `any(k in message.lower() for k in ("language", "prefer")) and any(f.type == "preference" for f in selected)`.

**Defect 3: False `conversation_history` Tag on Turn 1**
- *Problem*: `recent_turns` contains the current user turn, so `if recent_turns:` evaluates to `True` on the first turn.
- *Fix*: Tag `conversation_history` only when `len(recent_turns) > 1` (i.e. prior turns exist).

### 3.4 Dynamic Recalculation & Cache Safety
**Defect 1: Stale Zodiac Sign**
- *Problem*: `if profile.zodiac is None:` prevents recalculating zodiac when a user corrects their `date_of_birth`.
- *Fix*: In `_apply_profile_fact()`, if `fact.key == "date_of_birth"`, always recompute `profile.zodiac = compute_zodiac(profile.date_of_birth)`.

**Defect 2: Caching Error / Fallback Responses**
- *Problem*: Placing `self.cache.set(cache_key, response_text)` outside the `try...except` block caches fallback error messages.
- *Fix*: Place `self.cache.set(...)` directly inside the `try` block immediately after a successful `llm_provider.generate(...)`.

---

## 4. How to Debug Issues Step-by-Step

### 4.1 Reproduce with a Minimal Script
Never debug inside a large test run or by manually clicking in the browser. Write a 10-line standalone python one-liner or test snippet using `.venv/bin/python3 -c "..."`.

Example:
```bash
.venv/bin/python3 -c "
import asyncio
from app.chat.service import ChatService
from app.brain.store import InMemoryGraphStore

async def run():
    svc = ChatService(graph_store=InMemoryGraphStore())
    res = await svc.chat('u1', 's1', 'My test message')
    print(res)

asyncio.run(run())
"
```

### 4.2 Inspect State Transitions
When debugging memory or context selection:
1. Print stored facts before and after the turn:
   ```python
   print(await svc.graph_store.get_facts(user_id))
   ```
2. Print selected context and score calculations:
   ```python
   selected, tags = svc.selector.select(message, profile, facts, turns)
   print("Selected:", selected, "Tags:", tags)
   ```
3. Check short-term turns:
   ```python
   print(await svc.short_term.get(session_id))
   ```

### 4.3 Environment & Process Sanity Check
- Always verify the Python binary being invoked is `.venv/bin/python3`:
  ```bash
  .venv/bin/python3 -c "import sys; print(sys.executable)"
  ```
- Verify all dependencies are satisfied:
  ```bash
  .venv/bin/pip check
  ```

