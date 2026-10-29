# Shared Brain Response Quality Evaluation Framework

## 1. Executive Summary & Purpose

The **Shared Brain** is a dual-memory architecture powering the `MyNaksh` conversational astrology and life-guidance platform. It reconciles two distinct operational layers:
1. **Short-Term Conversational Memory**: A localized, TTL-evicted sliding-window deque (`ShortTermMemory`) maintaining immediate dialogue turns and resolving conversational flow (e.g., pronouns, multi-turn follow-ups).
2. **Long-Term Graph Memory**: A durable semantic graph (`GraphStore` / `Neo4jGraphStore`) maintaining permanent entities, profiles, goals, preferences, and astrological placements across sessions.

This framework defines a rigorous, quantitative evaluation methodology to measure how the Shared Brain improves response quality compared to:
- A **Stateless Baseline** (zero memory across turns and sessions).
- A **Naive Memory Baseline** (appending entire unindexed chat histories into system prompts).

The framework assesses response quality across **six core dimensions**:
1. **Memory Accuracy**
2. **Context Relevance**
3. **Personalization**
4. **Conversation Consistency**
5. **Irrelevant Context Suppression**
6. **Memory Persistence**

---

## 2. Evaluation Architecture Overview

The end-to-end evaluation lifecycle follows the canonical pipeline:

```
[User Query] 
     │
     ▼
[Short-Term Turn Appended] ──> [Session History Window]
     │
     ▼
[Profile & Fact Retrieval] ──> [Candidate Facts from GraphStore]
     │
     ▼
[Context Selection Engine] ──> [Hybrid Scoring & Negative Suppression]
     │
     ▼
[Prompt Construction] ───────> [Targeted LLM Payload (Zero Context Contamination)]
     │
     ▼
[Inference Generation] ──────> [Response Quality Evaluation Suite]
     │
     ▼
[Post-Turn Fact Update] ─────> [Idempotent Upsert & Knowledge Graph Evolution]
```

---

## 3. The Six Evaluation Dimensions

### 3.1 Dimension 1: Memory Accuracy

#### Operational Definition
The precision, recall, and structural fidelity with which user-declared facts (names, milestones, career transitions, birth details, and language preferences) are captured, parsed, normalized into ISO standards, and persisted in the knowledge graph without hallucination or corruption.

#### Quantitative Formulas

1. **Fact Extraction Precision ($P_{extract}$)**:
   $$\text{Precision}_{extract} = \frac{|F_{extracted} \cap F_{ground\_truth}|}{|F_{extracted}|}$$

2. **Fact Extraction Recall ($R_{extract}$)**:
   $$\text{Recall}_{extract} = \frac{|F_{extracted} \cap F_{ground\_truth}|}{|F_{ground\_truth}|}$$

3. **Attribute Normalization Fidelity ($Fidelity_{attr}$)**:
   $$\text{Fidelity}_{attr} = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{Norm}(\text{attr}_i) == \text{Expected}(\text{attr}_i))}{N}$$
   Specifically evaluated on relative date expressions (e.g., `"born in 2004 on 3rd month from march and on 26th"` $\rightarrow$ strict ISO-8601 `"2004-06-26"`).

4. **Semantic Relationship Accuracy ($SRA$)**:
   $$\text{SRA} = \frac{\text{Correctly Assigned Graph Relations } (HAS\_GOAL, HAS\_PROFILE, PREFERS, INTERESTED\_IN)}{\text{Total Extracted Entities}}$$

#### Automated Evaluation Protocol
- **Golden Extraction Corpus**: 97 test cases in `tests/test_prompts.py` and scenario tests in `tests/test_scenarios.py`.
- **Target Threshold**: $P_{extract} \ge 95\%$, $R_{extract} \ge 92\%$, $Fidelity_{attr} \ge 98\%$.

---

### 3.2 Dimension 2: Context Relevance

#### Operational Definition
The degree to which facts injected into the LLM prompt directly address the user's immediate intent. The context selector must prioritize high-signal facts while constraining prompt size to eliminate token waste.

#### Quantitative Formulas

1. **Context Precision@K ($P@K$)**:
   $$\text{Precision@K} = \frac{\sum_{i=1}^{\min(K, |S|)} \mathbb{I}(\text{Relevance}(fact_i, \text{Query}) > 0)}{\min(K, |S|)}$$
   Where $S$ is the selected facts set and $K$ is the configured maximum limit (`settings.memory_top_k = 5`).

2. **Hybrid Context Relevance Score ($Score$)**:
   Each candidate fact is ranked using the unified scoring formula:
   $$\text{Score}(f, q) = \text{Overlap}(f, q) + \text{DomainBoost}(f, q) + 0.5 \cdot \text{Confidence}(f) + \text{RecencyBoost}(f)$$
   Where:
   - $\text{Overlap}(f, q) = | \text{tokens}(q) \cap \text{tokens}(f) |$ (excluding stopwords).
   - $\text{DomainBoost}(f, q) \in \{+2.0, +3.0\}$ for categorical and intent matches (e.g. career goals, zodiac inquiries).
   - $\text{RecencyBoost}(f) = \frac{0.5}{1.0 + \frac{\Delta t}{86400}}$ (where $\Delta t$ is age in seconds).

3. **Context Utilization Ratio ($CUR$)**:
   $$\text{CUR} = \frac{\text{Count of Injected Facts Explicitly Grounded in Generated Response}}{|S|}$$

#### Automated Evaluation Protocol
- Given a query targeting career transition, assert that $100\%$ of facts in `selected_facts` possess `type == 'goal'` or domain relevance $> 0$.
- Verify that `context_used` emits exact telemetry tags (`"career_goal"`, `"shared_brain"`).
- **Target Threshold**: $P@K = 100\%$, $CUR \ge 85\%$.

---

### 3.3 Dimension 3: Personalization

#### Operational Definition
The capability of the system to generate empathetic, bespoke guidance that incorporates the seeker's identity, birth placements, career timeline, and language preferences, avoiding generic horoscope templates.

#### Quantitative Formulas

1. **Personalization Specificity Index ($PSI$)**:
   $$PSI = \frac{|E_{response} \cap (E_{profile} \cup E_{brain})|}{|E_{response\_entities}|}$$
   Where $E_{response}$ represents named entities, astrological coordinates, and milestones generated in the assistant's output, and $E_{profile} \cup E_{brain}$ represents known user ground truth.

2. **Astrological Alignment Factor ($AAF$)**:
   $$AAF = \mathbb{I}(\text{Response aligns with } \text{ZodiacArchetype}(user\_profile.zodiac))$$
   Evaluates that advice for an Aries user reflects initiative/action orientation, while a Cancer user receives reflective, intuitive emotional grounding.

3. **A/B Differential Lift ($\Delta_{pers}$)**:
   $$\Delta_{pers} = \text{Human/Judge Score}(\text{Shared Brain Response}) - \text{Human/Judge Score}(\text{Stateless Response})$$

#### Automated Evaluation Protocol
- Compare stateless baseline responses against Shared Brain responses for identical prompts with stored profile data (e.g., Sun in Leo, career target AI engineering in 2026).
- Evaluate presence of user name (`"Rahul"`), zodiac energy (`"Leo"`), and specific milestone (`"2026"`).
- **Target Threshold**: $PSI \ge 0.75$, $\Delta_{pers} \ge +2.2$ on a 5-point Likert scale.

---

### 3.4 Dimension 4: Conversation Consistency

#### Operational Definition
The temporal, logical, and factual continuity of dialogue across multiple sequential turns. The model must resolve conversational references (e.g., pronouns like *"Why do you say that?"*, *"How does that affect my plan?"*) without contradicting previously stated guidance.

#### Quantitative Formulas

1. **Dialogue Contradiction Rate ($DCR$)**:
   $$\text{DCR} = \frac{\text{Count of Contradictory Assertions Across Dialogue Sequence}}{\text{Total Dialogue Turns } T}$$

2. **Pronoun & Anaphora Grounding Accuracy ($PGA$)**:
   $$PGA = \frac{\text{Successfully Grounded Conversational References}}{\text{Total Anaphoric References Tested}}$$

3. **Short-Term Turn Cohesion ($STC$)**:
   $$STC = 1.0 - \text{DCR}$$

#### Automated Evaluation Protocol
- Execute multi-turn chains (Turn 1: *"What should I focus on for my career?"* $\rightarrow$ Turn 2: *"Why do you say that?"*).
- Assert `"conversation_history"` is present in `context_used`.
- Verify the assistant turn history is correctly formatted and passed in `llm_messages`.
- **Target Threshold**: $DCR = 0.0\%$, $PGA \ge 98\%$.

---

### 3.5 Dimension 5: Irrelevant Context Suppression

#### Operational Definition
The strict suppression of non-pertinent long-term memories when answering queries in an orthogonal domain. When a user asks an out-of-domain question (e.g. asking for cookie recipes, pure math, or plant biology), the system must NOT inject unrelated personal memories (e.g., career switch, culinary preference) into the LLM prompt.

#### Quantitative Formulas

1. **Context Contamination Rate ($CCR$)**:
   $$CCR = \frac{\text{Count of Irrelevant Stored Facts Injected into Prompt}}{\text{Total Facts Injected into Prompt}}$$

2. **Negative Rejection Rate ($NRR$)**:
   $$NRR = \frac{\text{Out-of-Domain Inquiries Resulting in Exactly } \text{selected\_facts} == []}{\text{Total Out-of-Domain Inquiries Evaluated}}$$

3. **Telemetry Cleanliness ($TC$)**:
   $$TC = \mathbb{I}(\text{"shared\_brain"} \notin \text{context\_used} \land \text{"career\_goal"} \notin \text{context\_used})$$

#### Automated Evaluation Protocol
- Seed user graph with career goals and personal preferences.
- Submit queries across disjoint domains:
  - Biology: *"Can you explain how photosynthesis works in green plants?"*
  - Culinary: *"What is the secret recipe for chocolate chip cookies?"*
  - Mathematics: *"Calculate the square root of 144 plus 55."*
- Assert:
  - `selected_facts == []`
  - `"shared_brain" not in context_used`
  - `"career_goal" not in context_used`
- **Target Threshold**: $CCR = 0.0\%$, $NRR = 100\%$, $TC = 1.0$.

---

### 3.6 Dimension 6: Memory Persistence & Evolution

#### Operational Definition
The resilience of durable memory across session resets, application restarts, and temporal updates. Furthermore, when users update or correct information (e.g., revising their career target from 2026 to 2025), the system must perform an idempotent in-place update without creating duplicate or conflicting graph nodes.

#### Quantitative Formulas

1. **Cross-Session Recall Rate ($CSRR$)**:
   $$CSRR = \frac{|F_{recalled\_in\_session\_2} \cap F_{stored\_in\_session\_1}|}{|F_{stored\_in\_session\_1}|}$$

2. **Session Isolation Integrity ($SII$)**:
   $$SII = \mathbb{I}(\text{"conversation\_history"} \notin \text{context\_used}_{\text{session\_2}} \land \text{"shared\_brain"} \in \text{context\_used}_{\text{session\_2}})$$

3. **Idempotent Update Fidelity ($IUF$)**:
   $$IUF = \frac{\sum_{i=1}^{U} \mathbb{I}(\text{FactCountAfter}_i == \text{FactCountBefore}_i \land \text{ValueUpdated}_i)}{U}$$
   Where $U$ is the number of correction operations.

#### Automated Evaluation Protocol
- **Cross-Session Recall**: Session 1 declares career goal $\rightarrow$ Session 2 initializes with brand-new `session_id` $\rightarrow$ verify long-term memory is retrieved while short-term history remains isolated.
- **Idempotent Correction**: Store 2026 goal $\rightarrow$ Send *"Actually I will switch jobs in 2025"* $\rightarrow$ Assert graph store fact count for `goal:career` equals 1, node ID remains invariant, and metadata reflects `"2025"`.
- **Target Threshold**: $CSRR = 100\%$, $SII = 1.0$, $IUF = 100\%$.

---

## 4. Assessment Rubric

Each of the six dimensions is scored against a standardized 5-tier rubric:

| Score | Tier | Definition & Empirical Criteria |
|---|---|---|
| **5** | **Exceptional (Production-Grade)** | Zero errors. $100\%$ irrelevant context suppression, exact ISO date normalization, zero duplicate nodes on correction, seamless cross-session recall, $100\%$ telemetry accuracy. |
| **4** | **Strong (Meets Production Standards)** | High precision ($\ge 95\%$), correct memory retrieval, clean cross-session isolation, prompt guidance active for missing profile data. Minor latency variance. |
| **3** | **Adequate (Functional with Gaps)** | Basic memory retention works, but occasional fallback-to-recent context occurs or slight token leakage on ambiguous queries. |
| **2** | **Substandard (Defective)** | Irrelevant facts routinely leak into prompts; corrections create duplicate graph nodes; date normalization fails on non-standard phrasing. |
| **1** | **Critical Failure** | System crashes on missing profile data, unhandled exceptions in pipeline, total loss of memory across sessions, or hallucinations. |

---

## 5. Comparative Evaluation: Baseline vs. Shared Brain

| Dimension | Stateless Baseline | Naive Memory Buffer | Shared Brain (Dual-Memory) |
|---|---|---|---|
| **Memory Accuracy** | 0% (No memory) | Poor (Raw chat text, unparsed) | **$\ge 95\%$ (Structured facts, ISO normalized)** |
| **Context Relevance** | None | Low (Dumps last 50 turns blindly) | **$100\%$ ($P@K$ top-k filtered by hybrid score)** |
| **Personalization** | Low (Generic horoscopes) | Medium (High latency prompt bloat) | **High (Tailored Vedic + Jungian synthesis)** |
| **Conversation Consistency** | 0% across sessions | Degrades as window fills | **$100\%$ (Sliding short-term + durable graph)** |
| **Irrelevant Context** | Clean (No context) | Terrible (Pollutes with all past topics) | **$0.0\%$ Contamination (Strict negative suppression)**|
| **Memory Persistence** | None | Lost on session close | **$100\%$ Cross-session durable persistence** |

---

## 6. Automated Verification Harness in CI/CD

The continuous evaluation pipeline executes the automated verification suite via `pytest`:

```bash
# Run full suite including the 8 core scenario tests
.venv/bin/python3 -m pytest tests/test_scenarios.py -v

# Run complete project verification (115+ tests)
.venv/bin/python3 -m pytest tests/ -v
```

### Automated Scenario Mapping Matrix

| Scenario | Test Function | Primary Dimension Evaluated | Acceptance Gate |
|---|---|---|---|
| **Scenario 1** | `test_scenario_1_new_user` | Empty Memory & Clean Baseline | Status 200, 0 brain facts, 0 memory tags |
| **Scenario 2** | `test_scenario_2_create_long_term_memory` | Memory Accuracy & Fact Extraction | Confidence $\ge 0.70$, `HAS_GOAL`, timeframe extracted |
| **Scenario 3** | `test_scenario_3_retrieve_memory` | Context Relevance & Prompt Grounding | `career_goal` & `shared_brain` tagged |
| **Scenario 4** | `test_scenario_4_follow_up_question` | Conversation Consistency | `conversation_history` tagged, history formatted |
| **Scenario 5** | `test_scenario_5_new_session_using_previous_info` | Memory Persistence across Sessions | Cross-session recall 100%, session isolation 100% |
| **Scenario 6** | `test_scenario_6_irrelevant_memory` | Irrelevant Context Suppression | `selected == []`, `shared_brain` strictly excluded |
| **Scenario 7** | `test_scenario_7_user_correcting_info` | Idempotent Memory Evolution | Fact count unchanged, node updated in-place |
| **Scenario 8** | `test_scenario_8_missing_user_info` | Graceful Error & Fallback Handling | Missing Birth Protocol active, status 200 |
