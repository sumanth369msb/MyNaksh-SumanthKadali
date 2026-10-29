# Repository Rules & Architectural Standards — MyNaksh

This document defines the strict engineering rules, architectural standards, and operational invariants for `MyNaksh-SumanthKadali`. All contributors and automated agents must adhere to these rules.

---

## 1. Core Engineering Philosophy

1. **Clean & Simple Code**:
   - Avoid speculative abstractions, unnecessary design patterns, and bloated third-party dependencies.
   - Code must run seamlessly in constrained environments (e.g., macOS with RAM constraints, without requiring Homebrew or heavy external binaries).
   - Use standard library modules and existing dependencies in `requirements.txt` wherever possible.

2. **Zero Modification Without Prior Approval**:
   - Never modify application source code in `app/` without explicit verification, an approved plan, and user consent.
   - Retain 100% backwards compatibility for existing endpoints and contracts (`/health`, `/chat`, `/users`, `/users/{user_id}`, `/users/{user_id}/brain`).

3. **Deterministic Local Development & Zero-Dependency Testing**:
   - The test suite must pass with zero external dependencies (no running Neo4j container, no OpenAI API key).
   - `InMemoryGraphStore` and `MockLLMProvider` are first-class components, not afterthoughts. Any interface change on `GraphStore` or `LLMProvider` must be identically supported by both memory and production implementations.

---

## 2. Shared Brain Architecture & Invariants

1. **Dual-Store Strategy**:
   - **Short-Term Memory** is session-scoped (`session_id`), ephemeral, sliding-window bounded by `SHORT_TERM_MAX_MESSAGES` (default 20), and TTL-evicted by `SHORT_TERM_TTL_SECONDS` (default 3600).
   - **Shared Brain (Long-Term Memory)** is user-scoped (`user_id`), durable, and persisted as a graph of `User` and `Fact` nodes.

2. **Graph Schema Invariants**:
   - Nodes:
     - `User { id, name, date_of_birth, time_of_birth, birth_place, preferred_language, zodiac, metadata }`
     - `Fact { id, user_id, type, key, value, relation, confidence, source, metadata, created_at, updated_at }`
   - Canonical Fact ID: `{user_id}:{type}:{key}`.
   - Relationships:
     - `User -[:HAS_FACT]-> Fact`
     - The `relation` property on `Fact` and edge must reflect semantic intent:
       - `HAS_GOAL` for `type="goal"`
       - `PREFERS` for `type="preference"`
       - `INTERESTED_IN` for `type="interest"`
       - `HAS_PROFILE` for `type="profile"`
       - `HAS_FACT` for generic facts or zodiac attributes.

3. **Conflict Resolution & Idempotency**:
   - Upsert is keyed by `(user_id, type, key)`.
   - Subsequent updates (e.g., changing career goal timeframe or updating DOB) MUST overwrite the existing fact in place rather than appending a duplicate node.

4. **Profile & Fact Synchronization**:
   - When a profile is upserted (via `POST /users` or inside `POST /chat`), durable profile attributes (`name`, `date_of_birth`, `birth_place`, `preferred_language`, `zodiac`) must also be synchronized as `Fact` nodes in the Shared Brain so that neighborhood queries and `/users/{user_id}/brain` reflect complete user context.

---

## 3. Request Pipeline Order

The `ChatService.chat()` request pipeline must strictly follow this order:

```
POST /chat
  ├─ 1. Append user turn to short-term session memory
  ├─ 2. Upsert user profile (if provided) into User store and recompute zodiac
  ├─ 3. Sync profile attributes into Shared Brain Fact nodes
  ├─ 4. Extract durable candidate facts from current user message
  ├─ 5. Upsert extracted facts into Shared Brain (and update User node if profile fact)
  ├─ 6. Select relevant context: user profile + top-K Shared Brain facts + recent short-term turns
  ├─ 7. Build LLM prompt from current message + selected context only
  ├─ 8. Query LLM provider (or return cached response if hit)
  ├─ 9. Cache successful LLM response (NEVER cache fallback responses)
  ├─ 10. Append assistant turn to short-term session memory
  └─ 11. Return ChatResponse (response, user_id, session_id, context_used)
```

**Crucial Invariant**: Fact extraction and Shared Brain upsert (Steps 4 & 5) MUST occur BEFORE context selection (Step 6). This guarantees that facts provided in the current message are immediately available for context selection and prompt injection on the same turn.

---

## 4. Context Selection & Tagging Rules

1. **Scoring Formula**:
   - Calculate token overlap between message query and `f"{fact.type} {fact.key} {fact.value}"`.
   - Add domain keyword boosts (e.g. +3.0 for `career`/`job` on `goal` facts; +3.0 for `language`/`prefer` on `preference` facts).
   - Only apply confidence weighting (`+ fact.confidence * 0.5`) if the baseline relevance score is > 0. Never give zero-overlap facts an automatic positive score.
2. **Fallback-to-Recent & Irrelevant Context Suppression**:
   - If no facts score > 0, fallback may retrieve recent facts, BUT `"shared_brain"` context tag is ONLY emitted when facts demonstrate positive relevance (`score > 0`) to the query intent. This guarantees compliance with Spec Section 14 (*"Irrelevant context suppression: unrelated facts are not injected into unrelated queries"*) and Section 6 (*"Empty memory / no relevant context: allowed"*).
3. **Context Tags Invariants**:
   - `user_profile`: Emitted if a profile is present and attached.
   - `shared_brain`: Emitted ONLY if one or more facts with positive relevance (`score > 0`) are selected.
   - `conversation_history`: Emitted ONLY when prior conversation turns exist (i.e. `len(recent_turns) > 1`). Do not tag on turn 1 where only the current user message exists.
   - `career_goal`: Emitted if query mentions career/job intent AND a goal fact is selected.
   - `language_preference`: Emitted if query mentions language/prefer intent AND a preference fact is selected.

---

## 5. Cache Safety Rules

1. **Cache Key Composition**:
   - Must include: `user_id`, `session_id`, `message`, selected fact IDs, recent turns count/signature, and user profile state/hash.
2. **Never Cache Fallbacks**:
   - Only cache responses when the LLM provider completes successfully.
   - If `llm_provider.generate()` raises an exception, caught fallbacks must NOT be saved to cache.

---

## 6. Resilience & Graceful Degradation

1. **No Unhandled 500s on Upstream Failures**:
   - Graph store failures: Log warning, treat as empty facts, and proceed with conversation.
   - LLM provider failures: Log warning, return a degraded guidance message, do not crash the request.
2. **Validation**:
   - Blank or whitespace-only `user_id`, `session_id`, or `message` MUST be rejected with HTTP 422.

