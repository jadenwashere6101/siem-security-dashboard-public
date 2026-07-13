## ADDED Requirements

### Requirement: Version 2 adds a distinct temporary playground mode without replacing Version 1
The Detection Simulator SHALL provide two clearly distinct modes: `Existing Production Rule` for the current Version 1 behavior and `Temporary Playground Rule` for Version 2. The temporary playground mode SHALL reuse the existing simulator workspace, authentication boundary, rollback disclosure, and preview surfaces, and SHALL NOT replace or alter the semantics of Version 1 production-rule simulation.

#### Scenario: Analyst sees both simulator modes
- **WHEN** an authorized analyst or super administrator opens the Detection Simulator workspace
- **THEN** the workspace presents both `Existing Production Rule` and `Temporary Playground Rule` as distinct selectable modes

#### Scenario: Version 1 remains unchanged
- **WHEN** the user selects `Existing Production Rule`
- **THEN** the simulator behaves exactly as the existing production-rule simulation path behaves today

### Requirement: Temporary playground rules use an authoritative narrow declarative contract
The temporary playground mode SHALL accept only a backend-authoritative declarative rule object with exactly these fields: canonical `source`, matching canonical `source_type`, compatible `input_format`, optional `event_type`, exactly one `condition` object, `aggregation.type`, `aggregation.group_by_field`, integer `threshold`, integer `window_minutes`, `severity`, and optional `mitre_technique_id`.

The allowed values SHALL be:

| Contract field | Allowed values |
|---|---|
| `source` | `honeypot`, `bank_app`, `pfsense`, `nginx`, `azure_insights`, `opentelemetry` |
| `source_type` | exact canonical match for the selected source only |
| `input_format` | `raw_text`, `json_lines`, `json_array`, subject to source compatibility |
| `condition.field` | `source_ip`, `destination_ip`, `destination_port`, `username`, `event_type`, `event_outcome`, `http_status`, `action`, `severity` |
| `condition.operator` | `equals`, `not_equals`, `contains`, `starts_with`, `ends_with`, `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `in_list` |
| `aggregation.type` | `count` |
| `aggregation.group_by_field` | `source_ip`, `destination_ip`, `username`, `destination_port` |
| `severity` | `low`, `medium`, `high`, `critical` |

The allowed numeric ranges SHALL be `threshold` 1-100 and `window_minutes` 1-1440. Scalar string values SHALL be 1-256 characters, `event_type` when present SHALL be 1-64 characters and source-compatible, and `in_list` SHALL contain 1-20 values with homogeneous primitive type. No other request fields or dynamic expression syntax SHALL be accepted.

#### Scenario: Valid declarative rule is accepted
- **WHEN** an authorized request supplies all required contract fields with allowed values and source-compatible types
- **THEN** the backend accepts the rule for temporary evaluation

#### Scenario: Unsupported field is rejected
- **WHEN** a request supplies a `condition.field`, `aggregation.group_by_field`, or `event_type` that is not allowed for the selected source's normalized schema
- **THEN** the backend rejects the request before evaluation with a fail-closed validation error

#### Scenario: Unsupported syntax is rejected
- **WHEN** a request includes extra fields, multiple conditions, boolean chains, regex, SQL fragments, Python code, shell commands, table names, or function-like expressions
- **THEN** the backend rejects the request without executing any pipeline stage

### Requirement: Temporary playground evaluation is pasted-event-only
Version 2 temporary playground rules SHALL evaluate only the pasted or sample events included in the current simulation request. The temporary evaluator SHALL NOT read previously committed production `events`, `alerts`, simulation-history rows, or draft rows for threshold, dedup, or window evaluation, and SHALL NOT expose a history-aware mode in Version 2.

#### Scenario: Threshold is computed from request-scoped events only
- **WHEN** a temporary playground rule evaluates a set of pasted or sample events
- **THEN** the observed count, grouped entity evidence, and threshold result are derived only from those request-scoped events

#### Scenario: History-aware request shape is rejected
- **WHEN** a request attempts to enable blended production-history evaluation or references a stored draft or saved rule identifier
- **THEN** the backend rejects the request as unsupported in Version 2

### Requirement: Temporary playground evaluation stays inside the existing rollback-only simulator boundary
The temporary playground evaluator SHALL run only inside the existing simulator-owned database transaction that is always rolled back. It SHALL use only the simulator-owned connection, SHALL NOT open an independent writable production connection, SHALL NOT call `commit()`, and SHALL NOT call `core.audit_helpers.log_audit_event`.

#### Scenario: Successful temporary simulation leaves no durable rows
- **WHEN** a temporary playground rule run reaches alert, MITRE, and SOAR preview stages successfully
- **THEN** no row remains committed in `events`, `alerts`, `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `incidents`, `incident_alerts`, or `audit_log`

#### Scenario: Exception path still rolls back
- **WHEN** an unexpected exception occurs after the simulator has started temporary-rule evaluation
- **THEN** the simulator rolls back before the request completes and no row remains durable in any guarded table

### Requirement: No worker or external integration side effect may occur
Temporary playground runs SHALL remain preview-only. No durable pending row may become visible to playbook workers or response-action workers, and no external integration or third-party API call SHALL execute, including Slack, Teams, email, webhook, firewall, reputation, geolocation, or similar outbound services.

#### Scenario: SOAR preview remains non-executing
- **WHEN** a temporary playground alert preview matches a playbook with selected response actions and approval requirements
- **THEN** the response includes preview-only SOAR evidence and no worker-visible queue or execution row is created

#### Scenario: Third-party and integration calls stay bypassed
- **WHEN** a temporary playground run reaches any enrichment or response-preview path that would call an external system on the real path
- **THEN** the simulator returns stubbed or preview-only evidence and performs no outbound network call

### Requirement: Query and resource limits are enforced before evaluation
The temporary playground backend SHALL reject oversized or unbounded requests before evaluation begins. Version 2 SHALL enforce, at minimum, these limits: maximum 100 pasted/sample events, maximum 256 KB total input payload, maximum 8 KB per raw event, maximum 256 characters per scalar string value, maximum `window_minutes` 1440, maximum `threshold` 100, maximum `in_list` length 20, maximum 50 grouped result rows returned, and a bounded evaluator timeout or equivalent execution guard.

#### Scenario: Event-count limit is enforced
- **WHEN** a request includes more than 100 pasted or sample events
- **THEN** the backend rejects the request before parsing or evaluation

#### Scenario: Payload-size limit is enforced
- **WHEN** a request exceeds the maximum total payload or per-event size
- **THEN** the backend rejects the request before evaluation with a size-limit validation error

### Requirement: Temporary playground explainability is backend-authored
The temporary playground response SHALL explain, using backend-derived evidence only, whether input parsed or failed, how events normalized, whether the rule was valid and applicable, which grouped entity was evaluated, the observed count, configured threshold, evaluated window, threshold reached or not reached, selected severity, alert preview, MITRE preview, SOAR/playbook preview, approval requirements, selected response preview, and explicit confirmation that nothing persisted or executed.

#### Scenario: Threshold not reached is explained
- **WHEN** a temporary playground rule does not reach threshold for a grouped entity
- **THEN** the response includes the observed count, configured threshold, evaluated window, grouped entity, and explicit no-alert reason

#### Scenario: Invalid rule is explained without React re-evaluation
- **WHEN** the request includes an invalid operator, incompatible value type, or unsupported group-by field
- **THEN** the backend returns structured validation evidence and the frontend renders that evidence without recomputing rule logic

### Requirement: Temporary playground preview contracts reuse existing simulator surfaces
Temporary playground runs SHALL reuse the existing simulator's normalized-event output contract, pipeline visualization, explainability panel, alert preview structure, MITRE preview structure, playbook matching preview, SOAR preview structure, rollback disclosure, and analyst/super-admin RBAC boundary wherever those surfaces do not require semantic change.

#### Scenario: Preview surfaces stay consistent across both modes
- **WHEN** the user switches between production-rule mode and temporary-rule mode
- **THEN** the pipeline/result presentation stays structurally consistent while clearly labeling temporary-playground semantics

### Requirement: UI provides a guided builder with explicit non-persistence language
The existing Detection Simulator workspace SHALL extend to support temporary playground mode with a source selector, input-format selector, pasted or sample events, guided condition builder, aggregation selector, group-by selector, threshold, window, severity, optional MITRE selection, live plain-language summary, `Run Simulation`, and non-persistence controls such as `Reset Rule`, `Discard Draft`, or `Clear Builder`. The UI SHALL NOT include `Save Rule`, `Promote to Production`, Python, SQL, Sigma, KQL, SPL, or free-form query editors.

#### Scenario: Builder presents non-persistence controls only
- **WHEN** the user is in temporary playground mode
- **THEN** the workspace offers reset/discard language and does not display save or promotion actions

#### Scenario: Plain-language summary updates from form state
- **WHEN** the user changes builder inputs
- **THEN** the workspace updates a plain-language summary of the temporary rule without evaluating the rule in React

### Requirement: Accessibility and responsive layout remain first-class
The updated Detection Simulator workspace SHALL remain keyboard accessible, dark-theme compatible, responsive on desktop and narrow layouts, and free of new console errors caused by temporary playground functionality.

#### Scenario: Keyboard flow works across builder controls
- **WHEN** a keyboard-only user tabs through the temporary playground builder
- **THEN** focus moves through the mode selector, builder controls, run/reset actions, and results in a logical order with accessible labels

#### Scenario: Narrow layout stays usable
- **WHEN** the workspace is rendered at a narrow viewport
- **THEN** the builder and result panels remain usable without breaking the mode distinction or hiding rollback/non-persistence disclosure

### Requirement: Version 2 requires focused verification and no migration by default
Implementation of this capability SHALL include focused backend and frontend tests for contract validation, bounded temporary evaluation, alert/MITRE/SOAR preview, no external calls, no worker-visible rows, zero durable writes, Version 1 regression protection, RBAC, frontend no-evaluation behavior, responsive layout, keyboard accessibility, and no new console errors. Version 2 SHALL NOT add a rules table, drafts table, simulation-history table, or schema migration unless implementation proves a hard requirement and stops for explicit review.

#### Scenario: No migration is the expected path
- **WHEN** implementation of Version 2 completes without discovering a hard blocker
- **THEN** deployment proceeds with no schema migration and the verification record states that expectation explicitly
