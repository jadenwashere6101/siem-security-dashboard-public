## Why

Before NIST evidence mapping begins, Anakin needs a small, repeatable regression baseline that distinguishes correctness and safety failures from bounded defects and deferrable model-quality work. Existing tests cover most behavior, but there is no single canonical matrix tying representative analyst requests to those checks and to later production/browser acceptance.

## What Changes

- Define 15 canonical pre-NIST scenarios covering entity binding, search, references, workflows, evidence, planner repair, provider boundaries, memory, RBAC, approvals, and degraded behavior.
- Add a compact reusable result classification: `PASS`, `BLOCKING_FAIL`, `BOUNDED_FIX`, `DEFER`, and `NOT_RUN`.
- Map each scenario to existing deterministic coverage and add only missing matrix/result-contract assertions.
- Separate offline deterministic acceptance from later authorized VM and browser acceptance.
- Record the verified production planner route as Anthropic `claude-sonnet-5` while keeping all local synthesis profiles Ollama-backed; routing changes remain out of scope.
- Preserve a strict zero-provider-call offline gate and document minimal paid-canary discipline for later production execution.

## Capabilities

### New Capabilities

- `anakin-pre-nist-regression-acceptance`: Canonical regression scenarios, deterministic coverage mapping, result triage, and production/browser handoff requirements.

### Modified Capabilities

None.

## Impact

- Extends `core/ai/acceptance_harness.py` with narrowly scoped matrix and classification helpers.
- Adds focused acceptance-contract tests while reusing planner, conversation, SOC-tool, workflow, session-memory, provider-routing, accounting, RBAC, and approval suites.
- Adds no API, schema, provider-routing, prompt, workflow, UI, or production-runtime changes.
- Requires no VM sync for the Mac-only specification and test infrastructure; later live acceptance remains separately authorized.
