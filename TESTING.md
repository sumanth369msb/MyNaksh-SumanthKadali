# Testing & Evaluation Guide: MyNaksh Personalized Astrology Chat

## 1. Automated Test Suite Overview

MyNaksh includes an automated test suite comprising **117 automated tests** executed in under $0.2$ seconds with zero external dependencies (utilizing the built-in deterministic mock provider and in-memory graph backend).

### Test Coverage Breakdown:
* **`tests/test_chat.py` (10 tests)**: Core end-to-end integration tests covering chat endpoints, profile persistence, and health checks.
* **`tests/test_prompts.py` (97 tests)**: Comprehensive prompt formatting, Jungian/Vedic persona assertions, flexible date parser variations, and structured JSON extraction tests.
* **`tests/test_scenarios.py` (10 tests)**: The 8 core architectural evaluation scenarios plus adversarial edge cases.

---

## 2. The 8 Core Architectural Test Scenarios

The suite explicitly verifies the 8 scenarios specified in Section 8 of the technical specification:

1. **`test_scenario_1_new_user`**:
   * *Objective*: Cold-start behavior on turn 1.
   * *Verification*: Graceful initialization with zero prior facts, no `shared_brain` tag emitted.
2. **`test_scenario_2_create_long_term_memory`**:
   * *Objective*: Long-term memory creation.
   * *Verification*: Stating career transition ("I am planning to switch jobs to AI engineering in 2026") extracts fact and persists in the graph.
3. **`test_scenario_3_retrieve_memory`**:
   * *Objective*: Retrieving memory in future turns.
   * *Verification*: Inquiring about career advice retrieves the stored goal and tags `shared_brain` + `career_goal`.
4. **`test_scenario_4_follow_up_question`**:
   * *Objective*: Short-term conversational context utilization.
   * *Verification*: Referential questions ("Why do you say that?") use the sliding-window turn history (`conversation_history` tag).
5. **`test_scenario_5_new_session_using_previous_info`**:
   * *Objective*: Cross-session memory recall.
   * *Verification*: Starting a new `session_id` isolates short-term turns while preserving long-term facts across sessions.
6. **`test_scenario_6_irrelevant_memory`**:
   * *Objective*: Strict irrelevant context suppression.
   * *Verification*: Out-of-domain queries (e.g., photosynthesis) receive 0 memory facts and omit `shared_brain`.
7. **`test_scenario_7_user_correcting_info`**:
   * *Objective*: Idempotent in-place fact replacement.
   * *Verification*: Updating a career timeline (shifting from 2026 to 2025) updates the existing fact node in-place without creating duplicate nodes.
8. **`test_scenario_8_missing_user_info`**:
   * *Objective*: Graceful fallback on missing profile.
   * *Verification*: Requesting birth chart readings without birth details provides gentle guidance requesting birth date, time, and place without crashing.
9. **`test_scenario_adversarial_special_characters_and_escaping`**:
   * *Objective*: Input sanitization and robustness.
   * *Verification*: Handles JSON special characters, quotes, and symbols without query corruption.
10. **`test_scenario_adversarial_empty_and_whitespace_validation`**:
   * *Objective*: Defensive validation.
   * *Verification*: Rejects empty and whitespace-only payloads with clean HTTP 422 errors.

---

## 3. Evaluating Shared Brain Response Quality

A sophisticated evaluation framework is not required; response quality improvement enabled by the Shared Brain is evaluated across the following six core dimensions:

### 1. Memory Accuracy
* **Evaluation Method**: Replay scripted conversations and assert that extracted fact key/value pairs match what the user stated (e.g., DOB `"15 August 1995"` &rarr; ISO `1995-08-15`, birthplace `"Delhi"` &rarr; `Delhi`).
* **Evaluation Criteria**: Fact extraction precision & recall must be 100%, ensuring no entity corruption, field truncation, or hallucinated facts.

### 2. Context Relevance
* **Evaluation Method**: Assert that selected facts overlap with incoming query intent/tokens; irrelevant stored facts must not appear in `context_used` or the LLM prompt.
* **Evaluation Criteria**: Top-$K$ relevance scoring verifies only high-salience facts are injected into the active prompt window.

### 3. Personalization
* **Evaluation Method**: Verify generated responses explicitly reference stored name, zodiac, or career goals rather than generic advice.
* **Evaluation Criteria**: Persona-aligned astrological synthesis reflecting user energetic profile (e.g., Leo confidence, Virgo analytical discipline).

### 4. Conversation Consistency
* **Evaluation Method**: Check that follow-up answers align seamlessly with facts stored in prior turns of the same session without contradictions.
* **Evaluation Criteria**: Resolves conversational pronouns and references (e.g., *"Why do you say that?"*, *"Explain that transit again"*) using short-term conversation context.

### 5. Irrelevant Context Suppression
* **Evaluation Method**: Confirm that out-of-domain queries (e.g., photosynthesis, science, or general math) do not emit the `shared_brain` tag or surface unrelated stored facts in prompt context.
* **Evaluation Criteria**: 0% context leakage on zero-relevance queries (`selected = []`).

### 6. Memory Persistence
* **Evaluation Method**: Assert that facts survive across independent sessions and service restarts; facts must remain retrievable via `GET /users/{id}/brain` after starting a new `session_id`.
* **Evaluation Criteria**: 100% cross-session recall fidelity across disjoint session IDs.

---

## 4. Running the Tests

Execute all tests from the repository root:

```bash
# Run tests quietly
.venv/bin/python3 -m pytest tests/ -q

# Run with verbose output showing all 117 tests
.venv/bin/python3 -m pytest tests/ -v
```

