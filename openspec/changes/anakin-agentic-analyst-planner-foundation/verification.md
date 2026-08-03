## Readiness Findings

- `workflow_request_service.queue_workflow_request()` classified requests before authoritative conversation resolution. `workflow_orchestrator.run_workflow()` classified again at execution.
- Explicit workflow labels bypassed reinterpretation. Auto-routing used current payload keyword checks without thread conclusions, corrections, unresolved questions, or verified evidence.
- `investigation_planner.py` is a deterministic Deep Investigate tool-plan builder. The model did not select SOC tools.
- Canonical conversation envelopes on `POST /ai/workflows` and `POST /ai/workflows/requests` are the eligible planner boundary. Legacy stateless endpoints remain compatible.
- Repo Assistant, SOC Briefing, response/action mutation routes, and approval/apply routes remain isolated.
- Session memory already preserves analyst statements, corrections, model inferences, unresolved questions, and verified evidence with provenance/freshness as distinct state.

## Budget Measurements

| Packet | Serialized chars | Full planner prompt chars | Limit |
|---|---:|---:|---:|
| Quick Explain minimal | 900 | 2,282 | packet 4,200 / prompt 8,000 |
| Deep Investigate minimal | 903 | 2,285 | packet 4,200 / prompt 8,000 |
| Decision Support minimal | 903 | 2,285 | packet 4,200 / prompt 8,000 |
| Generate Artifact minimal | 904 | 2,286 | packet 4,200 / prompt 8,000 |
| Production-sized multi-entity/correction/evidence packet | 4,196 | 5,578 | packet 4,200 / prompt 8,000 |

The production-sized packet reserved final omission bookkeeping before item selection. It omitted whole low-priority items and preserved the current question and resolved entities. Initial prompts reserve 1,000 characters for bounded repair metadata; repair prompts receive an independent final size check before generation.

## Failure-Class Review

- A new auto-routed question cannot inherit the old workflow: current-turn planning runs after authoritative resolution and dispatch receives the validated capability as an explicit server-owned workflow.
- Explicit current entities cannot be replaced by model entities: plan entities must exactly equal server resolution both during validation and submission revalidation.
- Missing or stale evidence cannot validate as sufficient without relevant verified/thread state. A quick lookup requires exactly one approved read category.
- Planner categories translate to one existing approved SOC read request; there is no iterative tool loop.
- Invalid plans receive at most one bounded repair. Invalid repair, timeout, disabled provider, or oversized repair returns a non-executing response and never invokes sticky routing.
- Retry with the same client request ID bypasses planner generation and returns the original turn/request capability.
- Repo, SOC Briefing, mutation, and unknown capabilities/tools fail deterministic boundaries.
- Unsupported user statements remain typed corrections/statements. Plan output is stored as planner metadata, never verified evidence.
- No fix depends on exact production sentences or a growing keyword list. Paraphrase tests exercise semantic plan contracts through controlled provider results.

## Model Capability Measurement

Twelve repeated controlled-local provider runs produced valid consistent plans without repair. The configured Mac runtime is disabled, `local_configured=false`, and Ollama was not listening on `127.0.0.1:11434`, so actual `llama3.2:3b` structured-planning reliability could not be measured without changing runtime state. This is a readiness limitation; no model or configuration was changed.

## Regression Results

- Focused affected suites: 204 passed.
- Planner contract suite: 46 passed.
- Production-shaped planner integration: passed through planner packet, controlled provider, validation, `search_alerts` dispatch, response envelope, and PostgreSQL turn state.
- AI acceptance harness: 76 actions discovered, 76 covered, 0 failures.
- Full PostgreSQL suite: 2,497 passed, 16 failed. The 14 failures recorded at baseline `266fb35` remain; the additional two are current-HEAD stale frontend-control label assertions from the committed thread experience. No failure is in planner/conversation diff scope and there are zero new failures attributable to this change.

## Production Gate

No deployment or deployed `/siem/` browser-path verification was authorized. Implementation complete; production behavior unverified.
