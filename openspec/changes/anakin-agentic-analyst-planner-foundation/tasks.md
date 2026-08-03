## 1. Readiness and Contracts

- [x] 1.1 Trace current free-form routing, context resolution, tool selection, gateway/profile limits, session assertions, and isolated route boundaries against the implemented code.
- [x] 1.2 Document planner placement, transaction boundaries, strict plan contract, budget model, capability mappings, and the complete failure-class enforcement table.
- [x] 1.3 Add typed planner packet/plan contracts, strict parser/validator, bounded one-repair behavior, and safe planner-unavailable results.

## 2. Planner Integration

- [x] 2.1 Build a fit-by-construction planner packet from authoritative thread/entity/evidence state with provenance, freshness, omission, and size measurements.
- [x] 2.2 Integrate planning after server-owned resolution and before eligible conversation capability selection without holding a database lock during model generation.
- [x] 2.3 Dispatch validated direct, lookup, investigation, comparison, decision, artifact, clarification, and boundary plans through existing safe paths while preventing workflow reclassification.
- [x] 2.4 Preserve Repo Assistant, SOC Briefing, mutation/action, read-only Decision Support, and preview-only Generate Artifact boundaries.

## 3. Focused Verification

- [x] 3.1 Add unit tests for schema validation, semantic strategy mappings, entity/evidence provenance checks, budget enforcement, one repair, timeout/provider failure, and prohibited plans.
- [x] 3.2 Add three-paraphrase behavioral tests for lookup, priority, explanation, evidence, topic switch, comparison, correction, no-tool, ambiguity, and boundary intents.
- [x] 3.3 Add production-shaped PostgreSQL integration coverage from planner packet through controlled provider, dispatch, response envelope, and durable thread state.
- [x] 3.4 Add repeated-run local-model capability measurements when the configured local provider is available; report limitations without model or profile changes.
- [x] 3.5 Run Python compilation, focused PostgreSQL suites, prompt-budget and workflow-boundary tests, and the AI acceptance harness.

## 4. Final Gates

- [x] 4.1 Run the full PostgreSQL-backed repository suite once and compare failures against current-HEAD baseline with no new failures.
- [x] 4.2 Run `git diff --check` and `openspec validate anakin-agentic-analyst-planner-foundation --strict`.
- [x] 4.3 Review sticky-workflow, paraphrase, conflicting-state, evidence, malformed-plan, boundary, timeout, and nondeterminism variants and record remaining Spec 2/3 work.

## 5. Anakin Production Completion Gate

- [ ] 5.1 Before using working, done, fully verified, or production-ready language, follow `docs/anakin-production-acceptance-policy.md` and verify every affected workflow through `browser -> /siem/ -> nginx -> frontend -> backend -> worker/Ollama -> frontend-rendered result`, capturing workflow, browser/API/UI results, latency, pass/fail, root cause, mutation status, and remaining unverified behavior.
- [x] 5.2 Because this implementation phase forbids deployment and VM access, report exactly `Implementation complete; production behavior unverified.` and do not claim Anakin is now an intelligent analyst agent.

## 6. Production Integration Correction

- [x] 6.1 Register `agentic_analyst_planning` in the Ollama provider capability contract without weakening unsupported-provider checks or local-only/no-paid-fallback policy.
- [x] 6.2 Validate the original requested workflow before planner generation, repair, classification, or fallback; reject Repo Assistant, SOC Briefing, and unknown workflows deterministically.
- [x] 6.3 Add provider/gateway and orchestration/route regression tests proving generation reachability, original-intent boundary ordering, safe planner-unavailable behavior, and valid shortcut fallback.
- [x] 6.4 Run focused PostgreSQL-backed tests, AI acceptance harness, Python compilation, `git diff --check`, and strict OpenSpec validation.
