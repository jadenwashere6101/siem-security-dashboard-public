## Context

Anakin already has extensive planner, orchestration, evidence, workflow, provider, session-memory, RBAC, approval, and acceptance-harness tests. This change creates a compact pre-NIST gate by organizing that coverage around 15 analyst behaviors instead of duplicating implementation tests. Mac execution is provider-free. Production and browser execution remain separate, explicitly authorized work.

The current verified production contract for this acceptance plan is `agentic_planning` to Anthropic `claude-sonnet-5`; `fast_triage` remains Ollama `llama3.2:3b`, while guided/deep local profiles remain Ollama `llama3.1:8b` unless sanitized runtime evidence says otherwise. This change does not alter routing.

## Goals / Non-Goals

**Goals:**

- Publish one canonical 15-scenario matrix with exact prompts, expected workflow/profile, safety assertions, execution layers, and existing coverage references.
- Provide a small result record and deterministic triage into `PASS`, `BLOCKING_FAIL`, `BOUNDED_FIX`, `DEFER`, or `NOT_RUN`.
- Add focused tests for matrix completeness, coverage-reference integrity, routing expectations, paid-canary discipline, and classification precedence.
- Preserve zero provider traffic offline and minimize later paid planner calls.

**Non-Goals:**

- Fix regressions, tune models/prompts, redesign sync/async behavior, change routes, add observability infrastructure, or modify provider/accounting/workflow logic.
- Perform VM, browser, Anthropic, or Ollama acceptance in the Mac phase.

## Decisions

### Extend the existing harness with a manifest, not another runner

`acceptance_harness.py` will expose immutable scenario definitions and result classification. Each definition links to meaningful existing pytest coverage. A focused test verifies referenced test functions exist, preventing the manifest from becoming decorative. Alternatives—duplicating all workflow tests or building a database-backed orchestration runner inside the harness—would increase runtime and create a second source of truth.

### Keep results compact and explicit

Each result records scenario ID, layer, workflow, provider/profile, entity, evidence, safety, outcome, and concise reason. `NOT_RUN` is the default; a scenario cannot become `PASS` merely because it is present in the matrix. Blocking observations take precedence over bounded or deferrable observations.

### Use three execution layers

| Layer | Owner and scope |
| --- | --- |
| A | Mac deterministic tests with mocked providers, local PostgreSQL where available, and the offline harness. All 15 scenarios have mapped coverage. |
| B | Later authorized VM API/runtime checks using live IDs and one shared alert/source/thread where sensible. |
| C | Later browser checks through `/siem/`, covering rendered identity/evidence, lifecycle, clarification, preview labels, RBAC, and truthful failure states. |

### Canonical matrix

| ID | Scenario | Workflow/profile | Core offline proof |
| --- | --- | --- | --- |
| 01 | Specific Alert Quick Explain | auto/Quick Explain; planner + fast triage | Exact alert/evidence; no substitution |
| 02 | Broad Alert Search | auto/Quick Explain | Entityless bounded newest/high/30m lookup |
| 03 | Follow-Up Reference | auto/Quick Explain | Current source resolution or clarification |
| 04 | Decision Support | Decision Support/guided | Grounded recommendation; no action |
| 05 | Deep Investigation | Deep Investigate/guided | Async lifecycle, bounded grounded/partial result |
| 06 | Artifact Generation | Generate Artifact/guided | Preview-only, not applied/persisted |
| 07 | Evidence-Heavy Investigation | Deep Investigate/guided | Provenance, bounds, truncation, no false correlation |
| 08 | Ambiguous Request | planner clarification | No guessed entity or premature dispatch |
| 09 | Invalid Entity | Quick Explain | Truthful not-found; no fallback record |
| 10 | Planner Repair | planner only | Exactly one repair; typed failure; fixed bindings |
| 11 | Local Quick Explain | canonical direct surface/fast triage | Ollama-only synthesis; no Anthropic fallback |
| 12 | Anthropic Planner Canary | planner only | Mocked Anthropic contract offline; one later paid canary |
| 13 | Session-Memory Continuity | auto/Quick Explain | Same-thread entity/evidence; owner isolation |
| 14 | RBAC / Approval Safety | guarded recommendation/action preview | Viewer rejected; no unapproved mutation |
| 15 | Provider Unavailable | degraded path | Truthful failure; no stale success/provider crossing |

### Paid-call discipline

Offline tests mock all provider output and make zero network calls. Later production acceptance budgets one paid planner canary for scenario 12. Other live scenarios reuse a representative thread and are not repeated for stylistic variance; actual attempt counts and configured cost estimates must be recorded.

## Risks / Trade-offs

- **Coverage links can outlive behavioral relevance** → Link to exact test functions and review mappings when tests are renamed.
- **Static routing expectations can drift from production** → Treat sanitized effective runtime evidence as authoritative during Layer B; this change records the currently verified Anthropic route without changing it.
- **Planner/model nondeterminism and latency** → Classify correctness/safety failures strictly, but defer stylistic variance, model tuning, and accepted latency optimization.
- **Known `display_alias: None` drift and source-name aliases** → Baseline as bounded risks unless tests prove wrong entity/evidence behavior, which promotes them to blocking.
- **Synchronous planner/HTTP architecture and provider latency** → Measure the existing timeout chain during later live acceptance; do not redesign it in this change.
- **Natural Ollama/Tailscale/provider availability** → Inject failures only offline; never create a production outage.

## Migration Plan

No schema or runtime migration exists. Mac adds specification/test infrastructure. VM and browser acceptance occur only after commit, deployment, and explicit authorization. Rollback is removal of the manifest and focused tests.
