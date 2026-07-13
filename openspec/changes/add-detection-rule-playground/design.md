## Context

Version 1 of the Detection Simulator already established the load-bearing architecture this change must preserve: the simulator calls production parser, normalization, alert-enrichment, playbook-matching, and SOAR-preview code inside one transaction that is always rolled back, and it explicitly avoids any `audit_log` write or external integration execution. That rollback-safe boundary is the approved foundation for Version 2.

The new need is narrower than "custom detections" in general. Analysts want a guided playground to answer questions such as "would repeated failed logins from this source trigger an alert?" or "what would the SOAR preview look like if this condition crossed threshold?" The architecture audit behind Version 2 already concluded that the safe approach is to reuse the Version 1 simulator workspace and preview contracts while adding only a constrained temporary-rule evaluator. This change must not redesign the whole detection engine, introduce a DSL that becomes a shadow query language, or imply parity with production detectors that do not yet exist.

## Goals / Non-Goals

**Goals:**

- Add a second simulator mode for temporary playground rules without regressing the existing production-rule simulation path.
- Keep temporary-rule evaluation inside the existing simulator-owned transaction and guarantee unconditional rollback.
- Reuse production parser/normalizer paths, normalized-event contracts, MITRE preview, alert preview, playbook matching, SOAR preview, explainability surfaces, and RBAC boundaries wherever unchanged reuse is possible.
- Define one authoritative declarative contract with exact validation and bounded resource usage.
- Make playground semantics explicit, including how threshold/window evidence is computed and how the result differs from a production detector.

**Non-Goals:**

- Arbitrary Python, arbitrary SQL, shell commands, dynamic imports, custom expressions, user-supplied table names, or direct database access.
- Persisted drafts, simulation-history storage, shared rule libraries, promotion-to-production, generated production detectors, Sigma/KQL/SPL import/export, or multi-condition boolean trees.
- Replacing Version 1 or refactoring the production ingest/detection pipeline into a new generalized rule engine.
- VM deployment work in this change. Phase 7 exists only as a later handoff plan.

## Decisions

### Preserve the Version 1 rollback boundary and add a small evaluator inside it

The playground path should execute in the same simulator transaction model as Version 1: simulator-owned connection, no independent writable connection, no `commit()` path, unconditional `rollback()` in success and failure paths, and no call to `log_audit_event`. The temporary evaluator runs after parsing/normalization and before preview assembly, but still within the same rollback-only request flow.

Alternative considered: a separate service or background worker for temporary rules. Rejected because it would duplicate containment logic, enlarge the blast radius, and create a second safety boundary to verify.

### Make the declarative temporary-rule contract authoritative and intentionally narrow

Version 2 should support one condition and one aggregation model, plus grouping for threshold evidence. The authoritative backend contract is:

| Field | Type | Allowed values / validation |
|---|---|---|
| `source` | string | One of `honeypot`, `bank_app`, `pfsense`, `nginx`, `azure_insights`, `opentelemetry` |
| `source_type` | string | Must exactly match the canonical source pair for `source` |
| `input_format` | string | `raw_text`, `json_lines`, or `json_array`; must be compatible with selected source |
| `event_type` | string or null | Optional exact-match filter; 1-64 chars; if present must be one of the normalized event types that the selected source can emit |
| `condition.field` | string | One of `source_ip`, `destination_ip`, `destination_port`, `username`, `event_type`, `event_outcome`, `http_status`, `action`, `severity` |
| `condition.operator` | string | `equals`, `not_equals`, `contains`, `starts_with`, `ends_with`, `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `in_list` |
| `condition.value` | string, number, or string[] | Scalar for all operators except `in_list`; list length 1-20 for `in_list`; each string max 256 chars |
| `aggregation.type` | string | `count` only |
| `aggregation.group_by_field` | string | `source_ip`, `destination_ip`, `username`, or `destination_port` |
| `threshold` | integer | 1-100 |
| `window_minutes` | integer | 1-1440 |
| `severity` | string | `low`, `medium`, `high`, `critical` |
| `mitre_technique_id` | string or null | Optional exact technique id in `Txxxx` or `Txxxx.xxx` form; no free-text MITRE payload |

Validation rules:

- The request must include exactly one condition object.
- Operators must be type-compatible: numeric comparison operators only for `destination_port` and `http_status`; string operators only for string fields; `in_list` items must all be the same primitive type.
- `group_by_field` must not be absent. Playground results are always thresholded per one grouped entity.
- `condition.field` and `group_by_field` must be allowed for the selected source's normalized schema; unsupported combinations fail closed.
- `condition.field == group_by_field` is allowed.
- No hidden expression expansion, regex, wildcard, nested JSON-path addressing, or function calls are permitted.

Alternative considered: supporting boolean chains or multiple aggregation types in V2. Rejected because that would turn the contract into a small programming language and materially raise semantic-drift and validation risk.

### Default to pasted-event-only evaluation and exclude blended production history from V2

Version 2 should evaluate temporary rules only against the events submitted in the simulation request, whether pasted manually or loaded from repo-provided sample payloads. It should not blend with already-committed production `events` or `alerts` for threshold/window evaluation, dedup suppression, or alert promotion logic.

Rationale:

- It keeps playground semantics clear: the result explains the provided test set, not ambient production traffic.
- It avoids the production-semantic drift of implying that a temporary DSL rule is already equivalent to a production detector wired into historical SQL over committed tables.
- It bounds cost and prevents expensive accidental scans of production history.

Alternative considered: optional history-aware mode in V2. Rejected for now because it weakens explainability, raises safety review scope, and creates user confusion about whether a temporary rule is "real." It remains future scope if later justified by a separate OpenSpec.

### Reuse production preview contracts without claiming production-detector equivalence

The playground should reuse parser/normalizer, normalized-event output, MITRE enrichment format, alert preview shape, playbook matching, approval preview, response preview, pipeline visualization, and explainability surfaces. But the evaluator itself is a new simulator-only component with documented playground semantics:

- It evaluates normalized event payloads in memory or via simulator-scoped staging only within the rollback transaction.
- It does not claim byte-for-byte equivalence with any future production detector until a separate implementation exists and is verified.
- Version 1 remains the only mode that claims production-rule simulation semantics.

### Keep SOAR preview read-only and worker-invisible

Temporary playground alerts may flow into the same preview assembly logic used by Version 1, but no durable `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `incidents`, `incident_alerts`, or `audit_log` rows may survive. No background worker may ever observe a pending row from a playground run, and no Slack, Teams, email, webhook, firewall, reputation, geolocation, or other external call may execute.

Alternative considered: limiting V2 to alert preview only. Rejected because the feature purpose explicitly includes MITRE and SOAR/playbook preview, and Version 1 already has the right preview scaffolding to reuse safely.

### Extend the existing Detection Simulator workspace instead of forking a new one

The frontend should keep one Detection Simulator workspace with a top-level mode selector:

- `Existing Production Rule`
- `Temporary Playground Rule`

The temporary-rule mode adds a guided builder and plain-language summary, but reuses the existing results, pipeline visualization, rollback disclosure, explainability panel, alert preview, MITRE preview, and SOAR preview sections. The frontend must render backend evidence only and must not re-evaluate condition logic in React.

## Risks / Trade-offs

- [DSL scope creep] → Keep one condition, one aggregation type, one group-by field, and an explicit future-scope list in both design and spec.
- [Users confuse playground semantics with production-detector semantics] → Use a hard mode split, persistent on-screen disclosure, and separate response metadata such as `simulation_mode=temporary_playground_rule`.
- [A future implementation accidentally opens a second connection or adds a commit path] → Require transaction-ownership tests, zero-durable-write tests, and explicit review of all simulator DB call sites.
- [Unsupported field/source combinations become silently permissive] → Validator-owned source/field compatibility matrix with fail-closed errors.
- [Large pasted payloads create expensive evaluation] → Enforce strict event-count, byte-size, string-length, threshold, window, and result-size limits before evaluation begins.
- [SOAR preview leaks into worker-visible durable rows] → Extend zero-write and separate-connection visibility tests across every guarded table and queue-adjacent table.

## Migration Plan

1. Mac AI implements the temporary-rule contract, validator, resource limits, and request/response schema inside the existing simulator route and engine boundary.
2. Mac AI implements the bounded evaluator, preview reuse, explainability payload, and focused backend tests proving zero persistence and no external calls.
3. Mac AI extends the existing Detection Simulator UI with the mode selector, builder, summary, validation, responsive layout, and focused frontend tests.
4. Mac AI runs focused regressions, full builds, browser verification, `git diff --check`, and `openspec validate add-detection-rule-playground --strict`.
5. After explicit authorization only, VM AI deploys the approved commit using the repository's Mac/VM policy. No migration is expected.

Rollback remains code-only. This change should add no migration, no persisted draft storage, and no production data mutation.

## Open Questions

- Should repo-owned sample-event fixtures for the builder live beside existing frontend fixtures, backend test fixtures, or a shared simulator sample catalog? Default expectation: shared simulator sample fixtures, but exact file placement can be decided during implementation.
- Should the temporary evaluator materialize normalized pasted events into a simulator-scoped temp structure inside the transaction or keep them fully in-process until preview assembly? Both are acceptable if the simulator owns the only connection and rollback remains unconditional.
