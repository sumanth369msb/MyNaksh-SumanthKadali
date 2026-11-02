# Multi-Agent System (MAS) Roadmap for MyNaksh

## Overview

MyNaksh is already structured like a modular AI architecture, even though it is currently implemented as a service-oriented monolith. The project is organized around domain-specific components such as profile management, memory, context selection, LLM access, astrology logic, and chat orchestration.

This makes it a strong candidate for evolution into a Multi-Agent System (MAS) without rewriting the whole application from scratch.

The goal is to transform the current pipeline into a coordinated set of specialized agents that communicate through a shared state and a central orchestrator.

---

## Why this project is a good MAS candidate

The repo already contains natural agent boundaries:

- `app/profile/` — user profile and identity facts
- `app/memory/` — short-term and long-term memory
- `app/brain/` — shared brain / graph store
- `app/context/` — context scoring and filtering
- `app/llm/` — LLM provider abstraction
- `app/astrology/` — astrological reasoning domain
- `app/chat/` — orchestrated conversation pipeline
- `app/api/` — external API surface

This is not random modularity. It already maps well to the roles of an agent-based system:

- Profile agent
- Memory agent
- Context agent
- Astrology agent
- Response generation agent
- Guardrail / safety agent
- Orchestrator agent

The current architecture calls these steps in order:

1. Validate input
2. Record short-term memory
3. Sync profile
4. Retrieve facts
5. Select context
6. Assemble prompt
7. Invoke LLM
8. Store updated memory

This is basically a workflow-driven MAS, even if it is implemented as a single service object today.

---

## MAS objective

Convert the single `ChatService`-style pipeline into:

- a central orchestrator
- specialized agents with clear responsibilities
- a shared memory/state schema
- agent-to-agent communication via explicit messages
- deterministic routing between agents
- optional asynchronous execution for independent tasks

The MAS should improve:

- modularity
- testability
- extensibility
- specialization of reasoning
- easier domain expansion
- better observability and debugging

---

## Target architecture

### High-level MAS design

```text
Client / API
   |
   v
Coordinator / Orchestrator Agent
   |--------------------------------------|
   |                                      |
   v                                      v
Profile Agent                         Memory Retrieval Agent
   |                                      |
   v                                      v
Context Selection Agent              Astrology Reasoning Agent
   |                                      |
   v                                      v
Response Generation Agent          Guardrail / Safety Agent
   |                                      |
   v                                      v
Memory Writing Agent / Shared Brain
```

### Core idea

The orchestrator does not directly do all work. Instead, it:

- receives the user request
- decides which agents are needed
- passes a structured state object
- collects outputs
- validates final response
- stores new memory facts when appropriate

---

## Proposed agent breakdown

### 1. Orchestrator Agent

Responsibilities:

- Accept incoming chat request
- Validate required fields (`user_id`, `session_id`, `message`)
- Determine message type
  - profile update
  - astrology query
  - memory lookup
  - general conversation
  - follow-up question
- Decide execution path
- Coordinate all agents
- Publish final payload to API caller

Example tasks:

- If message contains birth data, call `ProfileAgent`
- If message asks for horoscope / kundli / sun sign, call `AstrologyAgent`
- If memory is needed, call `MemoryAgent`
- If enough context exists, call `ContextAgent`
- Always call `GuardrailAgent` before finalizing response

---

### 2. Profile Agent

Responsibilities:

- Read, validate, and normalize user profile facts
- Update name, date of birth, time of birth, birthplace, preferred language
- Detect missing or incomplete profile data
- Convert raw user input to canonical profile schema
- Sync facts into the Shared Brain

Example tasks:

- `"My name is Rahul, born 15 August 1995 in Delhi"`
- `"I prefer Hindi"`
- `"I am a software engineer"`

Outputs:

- `profile_snapshot`
- `new_facts`
- `missing_profile_fields`

---

### 3. Memory Retrieval Agent

Responsibilities:

- Query short-term memory for session-specific context
- Query long-term brain memory for user facts
- Retrieve relevant historical facts, goals, preferences, and episodes
- Normalize graph results into a consistent structure
- Filter out irrelevant or noisy facts

Example tasks:

- Get last 5 conversation turns
- Retrieve career goals
- Retrieve birth chart facts
- Retrieve language preference

Outputs:

- `recent_turns`
- `relevant_facts`
- `memory_summary`

---

### 4. Context Selection Agent

Responsibilities:

- Rank candidate facts against the current message
- Use token overlap, keyword matching, recency, and confidence weighting
- Remove irrelevant context
- Ensure strict context suppression for out-of-domain questions
- Produce `Top-K` relevant context only

This agent is key to keeping the LLM grounded and reducing hallucination.

Outputs:

- `selected_context`
- `context_used_tags`
- `rejected_facts`

---

### 5. Astrology Agent

Responsibilities:

- Interpret astrology-specific queries
- Use user birth chart and profile data
- Infer sun sign, moon sign, ascendant, house influences, etc.
- Answer domain-specific questions with explicit reasoning grounded in known facts
- Ask for missing birth details when required

Example tasks:

- `"What is my sun sign?"`
- `"How does my birth chart align with my career goals?"`
- `"I am a Virgo; how should I think about my next 6 months?"`

Outputs:

- `astrology_insights`
- `missing_birth_data`
- `domain_reasoning`

---

### 6. Response Generation Agent

Responsibilities:

- Build the final LLM prompt
- Combine profile + selected memory + conversation context + astrology context
- Call the correct LLM provider
- Generate the user-facing answer in the correct tone
- Ensure answer is personalized and grounded

This agent should be the single point for LLM interaction.

Outputs:

- `response_text`
- `generation_metadata`
- `used_context_tags`

---

### 7. Guardrail / Safety Agent

Responsibilities:

- Detect hallucination risk
- Ensure answer references only grounded facts
- Reject unsafe or inappropriate content
- Prevent memory leakage across users
- Validate final output is compatible with system policy

This agent can also:

- block unsupported topic responses
- check for cross-user context leakage
- ensure the answer does not invent profile facts

Outputs:

- `passes_guardrails: bool`
- `warnings`
- `fallback_response` (if needed)

---

### 8. Memory Writing Agent

Responsibilities:

- Extract new facts after response generation
- Update graph memory and user profile facts
- Resolve conflicts and deduplicate facts
- Store new goals, preferences, life events, and user metadata
- Update or supersede older facts when needed

This is where your existing “Shared Brain” logic is most valuable.

Outputs:

- `stored_facts`
- `updated_facts`
- `conflict_updates`

---

## Shared agent state

All agents should operate on a single shared state object instead of isolated local-only memory.

Example state shape:

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class AgentState:
    user_id: str
    session_id: str
    message: str
    profile: Dict[str, Any] = field(default_factory=dict)
    recent_turns: List[Dict[str, Any]] = field(default_factory=list)
    memory_facts: List[Dict[str, Any]] = field(default_factory=list)
    selected_context: List[Dict[str, Any]] = field(default_factory=list)
    astrology_context: Dict[str, Any] = field(default_factory=dict)
    generation_payload: Dict[str, Any] = field(default_factory=dict)
    final_response: Optional[str] = None
    context_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

This enables:

- consistent orchestration
- easier debugging
- proper tracing of why a response was generated
- better observability for production use

---

## Agent communication model

A MAS should not rely on implicit side effects.

Instead, use a structured message contract for agent communication.

Example:

```python
from pydantic import BaseModel

class AgentMessage(BaseModel):
    user_id: str
    session_id: str
    message: str
    profile: dict | None = None
    facts: list[dict] = []
    context: list[dict] = []
    result: dict | None = None
    confidence: float = 0.0
```

Recommended patterns:

- explicit message payloads
- typed outputs
- async execution where independent
- central state tracking
- logs per agent call

---

## Proposed execution flow

### Phase 1: Input intake

The orchestrator receives the chat request.

Example:

```json
{
  "user_id": "user-123",
  "session_id": "session-456",
  "message": "I want to switch jobs to AI engineering in 2026. What should I focus on?"
}
```

---

### Phase 2: Profile sync

`ProfileAgent` checks whether the user profile exists or needs to be updated.

It may extract:

- name
- date of birth
- place of birth
- preferred language
- profile metadata

---

### Phase 3: Memory retrieval

`MemoryRetrievalAgent` reads:

- session short-term memory
- long-term shared brain
- existing user facts
- relevant past goals or preferences

---

### Phase 4: Context filtering

`ContextSelectionAgent` filters the memory facts to only those relevant to this message.

This is especially important because your project explicitly uses strict context suppression and relevance scoring.

---

### Phase 5: Domain-specific reasoning

If the request is astrology-related, `AstrologyAgent` evaluates the relevant facts and chart data.

If it is career / life planning, the same agent may still use memory and profile data but focus on grounded advice.

---

### Phase 6: Response generation

`ResponseGenerationAgent` creates the final answer from:

- user profile
- selected context
- conversation history
- applicable astrology reasoning
- LLM provider output

---

### Phase 7: Guardrail validation

`GuardrailAgent` checks:

- hallucination risk
- response groundedness
- memory leakage
- user-data privacy

If the answer fails, it may produce a fallback answer or request missing data.

---

### Phase 8: Memory write-back

`MemoryWritingAgent` stores newly extracted facts and updates the shared brain.

This ensures the system learns across sessions.

---

## Suggested repo mapping to MAS folders

A clean transition would look like this:

```text
app/
  agents/
    __init__.py
    orchestrator.py
    profile_agent.py
    memory_agent.py
    context_agent.py
    astrology_agent.py
    response_agent.py
    guardrail_agent.py
    memory_writer_agent.py
  mas/
    __init__.py
    state.py
    message.py
    workflow.py
    router.py
    telemetry.py
  chat/
    service.py
  api/
    routes.py
```

This preserves the current project while making the new MAS layer explicit.

---

## Recommended implementation phases

### Phase 1 — Refactor current pipeline to an orchestrator

Goal:

- Introduce a central orchestrator without breaking the existing service
- Move the current logic into a clearly defined sequence

Tasks:

- Create `app/mas/state.py`
- Create `app/mas/workflow.py`
- Implement orchestrator that calls existing service functions in order
- Keep `ChatService` as compatibility layer for now

---

### Phase 2 — Extract separate agent classes

Goal:

- Create the first set of agent classes around the existing modules

Tasks:

- `ProfileAgent` wraps profile logic
- `MemoryAgent` wraps memory retrieval logic
- `ContextAgent` wraps context scoring
- `ResponseAgent` wraps LLM provider usage

---

### Phase 3 — Add explicit inter-agent messages

Goal:

- Replace ad hoc function calls with typed messages and shared state

Tasks:

- Define message schema
- Make each agent return structured output
- Store results in shared state
- Trace agent execution in logs

---

### Phase 4 — Add guardrails and memory write-back

Goal:

- Ensure quality and persistence of system memory

Tasks:

- Add guardrail checks
- Add memory writer agent
- Add fact conflict resolution
- Add re-enablement for stored user memory

---

### Phase 5 — Add async orchestration

Goal:

- Improve performance and concurrency when multiple independent agents run

Tasks:

- Make independent agent tasks async
- Use `asyncio.gather()` for parallel retrieval tasks where appropriate
- Maintain ordering where needed

---

### Phase 6 — Production observability

Goal:

- Make the MAS monitorable in production

Tasks:

- Add per-agent logs
- Track selected context, rejected context, and agent route decisions
- Add telemetry for memory retrieval accuracy
- Add metrics for LLM cost and latency

---

## Architecture choices

### Option A — Lightweight custom MAS

Best for this project if you want to stay simple and control the system.

Pros:

- Minimal dependencies
- Direct integration with current modules
- Easy to debug
- Works well with a single Python service

Cons:

- Requires more custom orchestration code

Recommended if:

- you want a low-friction migration
- your current architecture is already clear and domain-specific

---

### Option B — LangGraph-based MAS

Best for more explicit agent workflows and state graphs.

Pros:

- Graph-based orchestration is very natural
- Good for multi-step reasoning
- Great observability and debugging
- Easy to add loops, retries, and branching

Cons:

- Adds another framework dependency
- Slightly more conceptual overhead

Recommended if:

- you want a more standard agent framework
- you prefer explicit graph state transitions
- you want richer orchestration patterns later

---

### Option C — CrewAI / AutoGen

Good for experimentation and quick prototype MAS.

Pros:

- Fast to set up
- Good for demonstration of role-based agents

Cons:

- Might not map as cleanly to this architecture
- More abstract and less aligned with your current service model

---

## Recommended choice for this repo

The best choice for MyNaksh is:

- Keep FastAPI as the API layer
- Add a custom orchestrator and agent classes
- Use a shared state object
- Optionally adopt LangGraph later for complex workflows

This keeps the change minimal and preserves the project’s existing design strengths.

---

## Suggested first set of agents to build

If you want an incremental path, start with these 5 agents:

1. `OrchestratorAgent`
2. `ProfileAgent`
3. `MemoryAgent`
4. `ContextAgent`
5. `ResponseAgent`

Then add:

6. `AstrologyAgent`
7. `GuardrailAgent`
8. `MemoryWriterAgent`

This progression allows you to validate the design before scaling into a richer multi-agent ecosystem.

---

## Migration strategy from the current project

### Step 1
Keep all current modules intact.

### Step 2
Create `app/mas/` package with:

- state
- workflow
- routing logic
- agent contracts

### Step 3
Wrap existing classes behind agent interfaces without changing business logic.

### Step 4
Replace direct function calls in `ChatService` with orchestrator-driven calls.

### Step 5
Add agent telemetry and response tags for each step.

### Step 6
Introduce persistent memory write-back and more advanced fact extraction.

---

## Benefits once migrated

After this MAS transition, MyNaksh will gain:

- clearer role separation
- easier experimentation with specialized reasoning
- better future extension (planner agent, scheduler agent, memory cleanup agent, etc.)
- more explainability
- better debugging of which context influenced responses
- easier integration with additional AI providers or external tools

---

## Example future MAS expansions

Once the base MAS is operational, you can add:

- `PlannerAgent` for long-term life planning
- `CalendarAgent` for timeline-based planning
- `RecommendationAgent` for personalized suggestions
- `MemoryCleanupAgent` to prune stale facts
- `EvaluationAgent` to judge answer quality
- `AnalysisAgent` to reason over user evolution over time

This becomes a true multi-agent cognitive system for astrology + personal guidance + memory-driven recommendations.

---

## Final recommendation

MyNaksh is already designed around a pipeline of specialized responsibilities. The next step is not to build a random swarm of agents, but to formalize those responsibilities into:

- a coordinator
- typed state
- specialized agents
- shared memory
- guardrails
- memory persistence

That gives you a practical, production-friendly MAS without losing the strengths of the current codebase.

---

## Summary

The roadmap is:

1. Add MAS orchestration layer
2. Wrap existing logic in specialized agents
3. Introduce shared state and agent messages
4. Add guardrails and memory write-back
5. Add async routing and telemetry
6. Expand with additional domain-specific agents over time

This is the natural evolution path for MyNaksh from a modular monolith into a scalable MAS architecture.

---

## Suggested file to create next

After this roadmap, the next useful artifact would be:

- `MAS_IMPLEMENTATION_PLAN.md` — detailed file-by-file implementation steps
- or `agents/README.md` — design docs for the actual Python agent layer

You can also begin by creating:

- `app/mas/state.py`
- `app/mas/workflow.py`
- `app/agents/orchestrator.py`

Those would be the first concrete code artifacts for the MAS migration.

---

## Suggested deliverables for the repo

Recommended initial deliverables:

- `app/mas/state.py`
- `app/mas/message.py`
- `app/mas/workflow.py`
- `app/agents/orchestrator.py`
- `app/agents/profile_agent.py`
- `app/agents/memory_agent.py`
- `app/agents/context_agent.py`

This will make the repo gradually evolve into a proper multi-agent architecture while preserving the current working code.

---

End of roadmap.
