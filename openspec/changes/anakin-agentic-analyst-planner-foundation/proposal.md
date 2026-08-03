## Why

Anakin currently fixes a conversational request to a workflow before interpreting authoritative thread context, so a new question can inherit an irrelevant prior strategy and repeat an old answer. A bounded analyst planner is needed above workflow selection so each eligible SIEM turn is reinterpreted, evidence needs are assessed, and only a validated read-only capability is dispatched.

## What Changes

- Add one policy-bounded planner for eligible SIEM conversation turns before Quick Explain, Deep Investigate, Decision Support, or Generate Artifact is selected.
- Build a compact, measured planner packet from the current question, resolved focus, relevant thread state, verified evidence and freshness, corrections, capability/tool boundaries, and latency class.
- Define and validate a strict structured plan covering current intent, prior-turn relationship, entities, evidence sufficiency, bounded strategy/capability/tool categories, clarification, stopping condition, confidence, and read-only safety.
- Permit at most one bounded structured-plan repair; invalid, unavailable, oversized, or boundary-violating plans fail safely without reverting to sticky workflow routing.
- Dispatch validated plans through existing capability and approved SOC read-tool paths, with no unrestricted iterative tool loop.
- Add production-shaped behavioral, PostgreSQL, prompt-budget, boundary, failure, and repeated-run planner evaluations.
- Route planner generation through a dedicated local-only `agentic_planning` profile using `llama3.1:8b`, without changing Quick Explain or other workflow profiles.

## Capabilities

### New Capabilities

- `anakin-agentic-analyst-planner`: Turn-level planning, strict plan validation, bounded repair, safe capability dispatch, and independent reinterpretation of eligible SIEM conversation turns.

### Modified Capabilities

None.

## Impact

The change affects the canonical SIEM conversation orchestration and async request dispatch paths, adds a planner module and planner-focused tests, records planner metadata in existing bounded conversation/workflow envelopes, and adds one planner-only local model profile. Session-memory ownership, PostgreSQL thread state, existing tool executors, capability implementations, response-action routes, Repo Assistant, SOC Briefing, existing workflow profile assignments, and frontend architecture remain unchanged.
