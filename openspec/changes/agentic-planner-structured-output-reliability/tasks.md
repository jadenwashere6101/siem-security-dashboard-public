## 1. Contract and validation

- [x] 1.1 Add one serializable authoritative planner-output contract covering fields, types, nullability, enums, conditionals, cardinalities, filters, formats, bounds, entity binding, artifact, clarification, and correction rules
- [x] 1.2 Align initial and repair prompts with the authoritative contract while preserving prompt-budget enforcement
- [x] 1.3 Replace prose-only validation results with bounded typed errors and explicit validated-field preservation state
- [x] 1.4 Enforce exactly one bare JSON object and reject fenced, prose-wrapped, multiple, or truncated JSON

## 2. Provider completion handling

- [x] 2.1 Extend normalized AI request metadata with sanitized provider completion state and stop reason
- [x] 2.2 Make Anthropic text-block extraction deterministic, exclude thinking content, and classify normal, exhausted, malformed/no-text, and transport/error outcomes
- [x] 2.3 Classify initial and repair output exhaustion before parser/validator entry without changing the 4,096-token ceiling
- [x] 2.4 Keep Anthropic temperature intentionally omitted, document the decision in code/tests, and preserve existing routing and accounting behavior

## 3. Repair and observability

- [x] 3.1 Rebuild the single bounded repair packet with typed errors, bounded invalid proposal data, the authoritative contract, and validated-state field preservation
- [x] 3.2 Persist and log bounded sanitized initial/repair reliability metadata, available token counts, plan size, final classification, and safe accounting linkage
- [x] 3.3 Prevent invalid, repaired-invalid, or truncated planner output from executing while retaining only the existing documented provider-unavailable explicit shortcut behavior

## 4. Offline regression coverage

- [x] 4.1 Add provider tests for stop reason, completion states, partial/no-text/thinking-only exhaustion, multiple text blocks, no reasoning exposure, unchanged max tokens, and omitted temperature
- [x] 4.2 Add planner tests for first-pass success, typed parse/schema/semantic/binding failures, syntactic truncation, successful/failed repair, repair exhaustion, and one-repair enforcement
- [x] 4.3 Add broad valid-plan and safety regression tests for direct answer, lookup, clarification, artifact, correction, unsupported tools, excess cardinality, mutation metadata, invalid filters, wrong identity, incompatible capability/action, ungrounded sufficiency, and invalid correction references
- [x] 4.4 Add orchestration/compact-metadata tests proving no execution on invalid or exhausted output and safe retention of both attempt classifications
- [x] 4.5 Add offline acceptance-harness fixtures for initial success, repair success, repair failure, and provider truncation with no real provider traffic
- [x] 4.6 Add an explicit regression proving validation depends on structured plan state rather than analyst wording

## 5. Verification and handoff

- [x] 5.1 Run focused planner, provider, orchestration, entity-binding, artifact/planner, and acceptance-harness tests available locally
- [x] 5.2 Run Python compilation, `git diff --check`, and `openspec validate agentic-planner-structured-output-reliability --strict`
- [x] 5.3 Review the complete diff and status, confirm no deterministic language interpretation, weakened safety rule, extra repair, real provider spend, VM access, deployment, commit, or push, and record any PostgreSQL-dependent tests that could not run
- [x] 5.4 Prepare the Mac-to-VM handoff and report `VM Sync Required: YES`; do not perform production verification without separate authorization

## 6. Anakin production completion gate

Anakin production completion gate:

Before reporting this Anakin change as working, done, fully verified, or production-ready, follow docs/anakin-production-acceptance-policy.md.

Automated tests, OpenSpec validation, frontend build success, service health, direct-backend localhost 200s, and offline acceptance harness success are necessary but not sufficient.

For every affected canonical workflow, verify the deployed browser path:
browser -> /siem/ -> nginx -> frontend -> backend -> worker/Ollama -> frontend-rendered result.

Capture Workflow, Browser-path result, Live API result, Latency, UI-rendered result, Pass/Fail, exact failure root cause, Production mutation performed: Yes/No, and remaining unverified behavior.

Confirm timeout compatibility across nginx, Gunicorn/backend, AI profile/provider, worker/runtime, polling, and terminal-state handling. Confirm the correct assistant/data source handled the request. Confirm safe workflows do not persist, apply, or mutate anything unless explicitly authorized.

Final totals must include Passed, Failed, and Unverified. Only report production-ready when Failed = 0 and Unverified = 0.

If browser-path verification was not performed, say exactly:
Implementation complete; production behavior unverified.
Do not say working, done, fully verified, or production-ready.
