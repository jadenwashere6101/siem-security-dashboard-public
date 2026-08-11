## Why

Anakin currently fixes a conversational request to a workflow before interpreting authoritative thread context, so a new question can inherit an irrelevant prior strategy and repeat an old answer. A bounded analyst planner is needed above workflow selection so each eligible SIEM turn is reinterpreted, evidence needs are assessed, and only a validated read-only capability is dispatched.

## What Changes

- Add one policy-bounded planner for eligible SIEM conversation turns before Quick Explain, Deep Investigate, Decision Support, or Generate Artifact is selected.
- Build a compact, measured planner fact packet from the current question, uniformly represented entity records with provenance, recorded thread state, verified evidence and freshness, corrections, capability/tool boundaries, and latency class without server-authored conversational interpretation.
- Define and validate a strict structured plan covering current intent, prior-turn relationship, planner-resolved entities and correction target, evidence sufficiency, bounded strategy/capability/tool categories, clarification, and confidence; derive stopping behavior and read-only safety on the server.
- Permit at most one bounded structured-plan repair; invalid, unavailable, oversized, or boundary-violating plans fail safely without reverting to sticky workflow routing.
- Dispatch validated plans through existing capability and approved SOC read-tool paths, with no unrestricted iterative tool loop.
- Add production-shaped behavioral, PostgreSQL, prompt-budget, boundary, failure, and repeated-run planner evaluations.
- Route planner generation through a dedicated local-only `agentic_planning` profile using the benchmark-selected `qwen3:14b`, without changing Quick Explain or other workflow profiles.
- Keep natural-language intent, relationship, reference resolution, entity selection, clarification, and capability choice model-owned; populate safety and execution metadata deterministically on the server and validate every selected entity after planning.
- Preserve the planner's bounded evidence intent as validated scalar requirements and translate those requirements into existing read-tool arguments without model-authored queries.
- Require every entity-bearing evidence lookup to carry the matching structured entity identity through plan validation, repair, tool translation, and execution so an exact alert or incident cannot degrade into an unrelated broad search.
- Ground final Quick Explain synthesis in a compact server-authored evidence envelope and reject or deterministically replace generic, unsupported, or evidence-free model prose.

## Capabilities

### New Capabilities

- `anakin-agentic-analyst-planner`: Turn-level planning, strict plan validation, bounded repair, safe capability dispatch, and independent reinterpretation of eligible SIEM conversation turns.

### Modified Capabilities

None.

## Impact

The change affects the canonical SIEM conversation orchestration and async request dispatch paths, adds a planner module and planner-focused tests, records planner metadata in existing bounded conversation/workflow envelopes, adds one planner-only local model profile, and extends existing read-tool schemas only where an exact structured entity filter is already supported by the canonical data path. Session-memory ownership, PostgreSQL thread state, capability implementations, response-action routes, Repo Assistant, SOC Briefing, existing workflow profile assignments, and frontend architecture remain unchanged.
