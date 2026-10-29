# Remediation Plan: MyNaksh Personalized Astrology Chat

## 1. Executive Summary

A comprehensive deep re-verification of `MyNaksh-SumanthKadali` was performed across the request lifecycle, graph persistence, memory extraction, context selection, caching, and error handling against `docs/context/technical_spec.md`.

All 23 automated tests pass (22 passed, 1 skipped due to optional Neo4j local environment). However, deep behavioral inspection and edge-case execution revealed 8 architectural and functional defects in the implementation that deviate from the specification.

This plan details each verified defect, root causes, exact planned code changes, and verification criteria for user review and approval prior to implementation.

---

## 2. Verified Findings & Root Cause Analysis

### Finding 1: Pipeline Execution Inversion in `ChatService.chat()`
- **Observed Behavior**: Candidate facts from the current message are extracted and upserted in `_update_memory()` at line 92, *after* context selection (line 72) and *after* LLM response generation (line 82).
- **Impact**: When a user introduces themselves or states a career goal in a single-turn message (e.g., *"I'm planning to switch jobs next year. What career advice do you have?"*), the newly stated fact is not available in `facts` when `select()` runs. The LLM generates a response stating *"I don't have your career details yet..."*, even though the user just provided them.
- **Spec Reference**: Section 1 (Architecture Request Flow) Steps 4 & 5 clearly state fact extraction and upsert occur *before* Step 6 (Context Selection) and Step 7 (Prompt Assembly).

### Finding 2: False Name Extractions & Greeting Drops in `RuleBasedExtractor`
- **Observed Behavior**:
  1. `IGNORE_PATTERNS` at line 29 causes any message starting with greetings (e.g. `"Hi, my name is Priya"` or `"Hello, I am Rohan born on 12 May 1990 in Mumbai"`) to return `[]`, discarding all facts.
  2. The name regex `r"(?:my name is|i am|i'm)\s+([A-Za-z][A-Za-z\-']*)"` matches common verbs and adjectives. An input like `"I am planning to switch jobs"` extracts `name = "planning"`, and `"I am confused"` extracts `name = "confused"`.
  3. Language extraction captures `"is"` from `"My preferred language is English"` and misses `"I prefer to speak Hindi"`.
  4. Extracted facts all default `relation="HAS_FACT"` instead of semantic relations (`HAS_GOAL`, `PREFERS`, `INTERESTED_IN`, `HAS_PROFILE`).
- **Spec Reference**: Section 2 (Semantic relations) and Section 3 (Long-term memory).

### Finding 3: Unconditional Relevance Scoring & Missing Tags in `ContextSelector`
- **Observed Behavior**:
  1. `score += fact.confidence * 0.5` is applied unconditionally to every fact, giving even completely unrelated facts a score >= 0.4. Consequently, `[f for s, f in scored if s > 0]` selects unrelated facts on queries like *"What is the weather today?"*, erroneously emitting the `shared_brain` tag.
  2. The spec defines `language_preference` as a standard context tag, but `ContextSelector` never emits it.
  3. On Turn 1 of any session, `recent_turns` has length 1 (the current user turn). `if recent_turns:` evaluates to `True`, falsely emitting `"conversation_history"` when no prior turns exist.
- **Spec Reference**: Section 4 (Context Selection & Tags).

### Finding 4: Missing Profile Fact Synchronization in `POST /users` & `POST /chat`
- **Observed Behavior**: Calling `POST /users` only writes to the `User` node and creates zero `Fact` nodes. A subsequent `GET /users/{user_id}/brain` returns `facts: []`.
- **Impact**: The Shared Brain graph is missing profile, preference, and zodiac facts for registered users.
- **Spec Reference**: Section 2 (Example stored facts graph diagram) and Section 3 line 83.

### Finding 5: Stale Zodiac on Date of Birth Update
- **Observed Behavior**: In `ChatService._apply_profile_fact()`, line 161 checks `if profile.zodiac is None:` before calling `compute_zodiac()`. If a profile already has a zodiac and the user updates their DOB, the zodiac is never updated.
- **Spec Reference**: Section 3 line 83: *"merge into the User node and recompute zodiac if date of birth is present"*.

### Finding 6: Poisoned LLM Response Cache on Provider Failure
- **Observed Behavior**: In `ChatService.chat()`, `self.cache.set(cache_key, response_text)` sits outside the `try...except` block at line 88. When `llm_provider.generate()` raises an exception, the fallback error message is stored in the TTL cache. Subsequent identical queries will return the fallback error message from cache even after the provider recovers.
- **Spec Reference**: Section 1 line 35 & Section 5 (Pluggable LLM Layer).

### Finding 7: Neo4j Cypher Syntax & Deletion Bugs
- **Observed Behavior**:
  1. In `app/brain/neo4j_store.py`, `ON CREATE SET f.created_at = $created_at` appears after a general `SET` clause. In Neo4j Cypher grammar, `ON CREATE SET` must immediately follow the `MERGE (f)` statement. This causes a syntax error if run against Neo4j.
  2. `clear_user()` executes `MATCH (u:User {id: $uid}) DETACH DELETE u`, leaving detached `Fact` nodes orphaned in the database.
- **Spec Reference**: Section 2 (Graph Schema) & Section 10 (Neo4j Store).

### Finding 8: Missing `@runtime_checkable` on Protocols
- **Observed Behavior**: Neither `GraphStore` nor `LLMProvider` is decorated with `@runtime_checkable`. Any `isinstance(store, GraphStore)` call raises `TypeError: Instance and class checks can only be used with @runtime_checkable protocols`.
- **Spec Reference**: Section 5 & Section 7 (Protocol definitions).

---

## 3. Proposed Implementation Plan

### Step 1: Reorder Request Lifecycle in `app/chat/service.py`
1. Reorder `chat()` execution to guarantee durable facts from the current turn are immediately available for context selection and prompt injection:
   - (1) Append user turn to short-term session memory.
   - (2) If `profile` is provided in request: upsert to graph store, compute zodiac if missing, and sync profile facts via `sync_profile_facts(profile)`.
   - (3) Load current `user_profile = await self._get_profile(user_id, profile)`.
   - (4) Extract candidate facts from current user message (`await self.extractor.extract(user_id, message)`).
   - (5) Upsert extracted facts into Shared Brain:
     - For profile facts: if `user_profile` is None, initialize `user_profile = UserProfile(user_id=user_id)`. Apply fact via `_apply_profile_fact(user_profile, fact)`, upsert user node, and sync the profile fact.
     - For all other facts: upsert into graph store via `upsert_fact(fact)`.
   - (6) Retrieve updated facts from graph store (`await self.graph_store.get_facts(user_id, limit=50)`).
   - (7) Select relevant context (`self.selector.select(message, user_profile, facts, recent_turns)`).
   - (8) Build prompt (`self._build_messages(...)`).
   - (9) Cache check & LLM generation: move `self.cache.set(...)` inside the `try` block so error fallbacks are never cached.
   - (10) Append assistant turn to short-term session memory.
   - (11) Return `ChatResponse`.
2. Introduce `ChatService.sync_profile_facts(profile: UserProfile)`:
   - Synchronizes `name`, `date_of_birth`, `birth_place`, `time_of_birth` (type `profile`, relation `HAS_PROFILE`), `preferred_language` (type `preference`, relation `PREFERS`), and `zodiac` (type `zodiac`, key `sun_sign`, relation `HAS_FACT`) into `Fact` nodes.
3. Update `_apply_profile_fact()`:
   - If `fact.key == "date_of_birth"`, always recompute `profile.zodiac = compute_zodiac(profile.date_of_birth)` regardless of whether `profile.zodiac` was previously set.

### Step 2: Fix Extraction Rules in `app/memory/extractor.py`
1. Refine `IGNORE_PATTERNS`:
   - Only return `[]` if the message consists *only* of conversational pleasantries (e.g., `re.match(r"^(hi|hello|hey|thanks|thank you|ok|okay)[\s,!.]*$", lower)`).
   - If a message starts with a greeting prefix followed by substantive content (e.g., `"Hello, my name is Priya"`), strip the leading greeting prefix and extract facts from the remainder.
2. Refine Name Extraction:
   - For `"my name is <Name>"`: match case-insensitively since the explicit phrase is semantically unambiguous.
   - For `"i am <Name>"` / `"i'm <Name>"`: require `<Name>` to start with an uppercase letter (`[A-Z][a-z\-']+`) and exclude common auxiliary verbs and adjectives (`planning`, `looking`, `confused`, `trying`, `born`, `hoping`, `ready`, `happy`, `interested`, `seeking`, `wondering`, `feeling`, `working`, `switching`).
3. Refine Language Extraction:
   - Instead of brittle positional regexes, scan for known languages (`known_languages`) when language/preference intent keywords (`prefer`, `preferred`, `language`, `speak`) are present in the turn.
4. Assign Semantic `relation`:
   - `HAS_GOAL` for `goal` facts.
   - `PREFERS` for `preference` facts.
   - `INTERESTED_IN` for `interest` facts.
   - `HAS_PROFILE` for `profile` facts.

### Step 3: Fix Context Scoring & Tags in `app/context/selector.py`
1. Calculate token overlap and keyword boosts first.
2. Only apply confidence weighting (`score += fact.confidence * 0.5`) if the baseline relevance score is > 0.
3. Resolve Fallback Paradox & Irrelevant Context Suppression:
   - Only emit `"shared_brain"` when facts with positive relevance (`score > 0`) are selected.
   - If no facts score > 0, do not falsely tag `"shared_brain"`, satisfying Section 14 ("Irrelevant context suppression") and Section 6 ("Empty memory / no relevant context: allowed").
4. Add `"language_preference"` tag when language keywords match and preference facts are selected.
5. Only tag `"conversation_history"` when `len(recent_turns) > 1` (prior turns exist).

### Step 4: Fix Profile Facts Synchronization in `app/api/routes.py` & `app/chat/service.py`
1. In `POST /users`, after upserting the `User` node, call `await service.sync_profile_facts(profile)` so that `GET /users/{user_id}/brain` returns the profile and zodiac facts immediately.
2. In `POST /chat` (via `ChatService.chat()`), when `profile` is provided, call `await self.sync_profile_facts(profile)` so chat-initiated profiles also populate the Shared Brain.

### Step 5: Fix Neo4j Cypher Statements in `app/brain/neo4j_store.py`
1. Rearrange `upsert_fact()` Cypher query to place `ON CREATE SET f.created_at = $created_at` immediately after `MERGE (f:Fact {id: $fact_id})`.
2. Update `clear_user()` to:
   ```cypher
   MATCH (u:User {id: $uid})
   OPTIONAL MATCH (u)-[:HAS_FACT]->(f:Fact)
   DETACH DELETE u, f
   ```

### Step 6: Protocol Annotations in `app/brain/store.py` & `app/llm/base.py`
1. Add `@runtime_checkable` to `class GraphStore(Protocol)`.
2. Add `@runtime_checkable` to `class LLMProvider(Protocol)`.

### Step 7: Clean Up Stale Artifacts
1. Remove trailing script artifacts in `misc/learn.md` (lines 128-129: `EOF\necho "done"`).

---

## 4. Verification & Validation Strategy

Post-approval verification will include:
1. **Regression Safety**: Execute full existing test suite (`.venv/bin/python3 -m pytest -v`) to confirm 100% of existing tests pass.
2. **First-Turn Context Verification**: Confirm that messages providing goals/details in turn 1 immediately receive personalized responses with appropriate context tags.
3. **Brain Facts Endpoint Verification**: Confirm that `POST /users` populates `/users/{id}/brain` with profile, preference, and zodiac facts.
4. **Zodiac Recalculation Verification**: Confirm that updating DOB dynamically updates the zodiac attribute.
5. **Cache Safety Verification**: Confirm that simulated LLM failure fallbacks are never retrieved from cache upon provider recovery.
6. **Extractor Robustness**: Verify greetings with facts (`"Hello, my name is Priya"`) are successfully extracted.

