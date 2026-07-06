## ADDED Requirements

### Requirement: Per-Execution Parameter Resolution
The playbook step executor SHALL resolve dynamic parameter values against the alert linked to the current execution before action-specific validation and adapter dispatch, so that each execution uses parameter values derived from its triggering alert rather than only static authored values.

#### Scenario: Dynamic source IP is resolved for block_ip
- **WHEN** a playbook execution reaches a `block_ip` step whose `params.source_ip` is the binding expression `{{alert.source_ip}}`
- **THEN** the executor SHALL resolve `source_ip` to the triggering alert's `source_ip` value for that execution before calling `require_unprotected_target` and dispatching to the firewall adapter.

#### Scenario: Static parameters are unchanged
- **WHEN** a playbook execution reaches a step whose `params` contain only literal static values (no binding expressions)
- **THEN** the executor SHALL pass those values through unchanged, preserving backward compatibility with existing playbook definitions.

#### Scenario: Mixed static and dynamic params
- **WHEN** a step's `params` object contains both static values and binding expressions
- **THEN** the executor SHALL resolve only the dynamic values and leave static values untouched.

### Requirement: Alert Field Binding Syntax
Playbook step parameter values SHALL support alert-field binding using the `{{alert.<field_name>}}` syntax, where `<field_name>` is a field from the alert surface defined in this capability's design.

#### Scenario: Supported alert field resolves correctly
- **WHEN** a param value is `{{alert.severity}}` and the triggering alert has `severity: "critical"`
- **THEN** the resolved value for that param SHALL be `"critical"` for that execution.

#### Scenario: Unsupported field is rejected at definition time
- **WHEN** a playbook definition is saved with a param value `{{alert.nonexistent_field}}`
- **THEN** definition-time validation SHALL reject the definition with a clear validation error.

### Requirement: Definition-Time Binding Validation
The playbook registry (and API layer that persists definitions) SHALL validate binding syntax and referenced field names at definition save time, in addition to existing action-name validation.

#### Scenario: Malformed binding expression is rejected
- **WHEN** a playbook definition is saved with a param value containing `{{` that does not conform to the allowed `{{alert.<field>}}` or `{{execution.<field>}}` pattern
- **THEN** definition-time validation SHALL reject the definition.

#### Scenario: Valid binding passes validation
- **WHEN** a playbook definition is saved with `params.source_ip: "{{alert.source_ip}}"` on a `block_ip` step
- **THEN** definition-time validation SHALL accept the definition.

### Requirement: Security Boundaries for Binding
Parameter binding SHALL be field-lookup only, SHALL NOT execute arbitrary code or queries, and SHALL apply existing safety policies to resolved values.

#### Scenario: Protected-target policy applies to resolved IP
- **WHEN** a `block_ip` step's `params.source_ip` resolves to an IP on the protected-target list
- **THEN** the step SHALL be rejected by `require_unprotected_target` exactly as it would for a static protected IP.

#### Scenario: Binding does not access other alerts
- **WHEN** parameter resolution runs for an execution
- **THEN** it SHALL load fields only from the alert identified by that execution's `alert_id`, not from any other alert or external source.

### Requirement: Missing-Field Fail-Closed Behavior
When a dynamic binding cannot be resolved to a concrete value at execution time, the step SHALL fail with a defined error rather than proceeding with a null or empty target.

#### Scenario: Missing nullable field fails the step
- **WHEN** a param binds to `{{alert.reputation_score}}` and the alert's `reputation_score` is null
- **THEN** the step SHALL fail with a binding error and SHALL NOT dispatch to the adapter.

#### Scenario: Missing alert context fails the step
- **WHEN** an execution has no `alert_id` or the alert row no longer exists
- **THEN** any step with dynamic bindings SHALL fail rather than falling back to static authored values silently.

### Requirement: Engine-Only Change Boundary
This change SHALL define engine capability requirements only. It SHALL NOT author playbook content, SHALL NOT modify application source code as part of this spec-writing step, and SHALL NOT create `playbook_definitions` rows.

#### Scenario: No functional files touched by spec authoring
- **WHEN** this change is reviewed via `git status`/`git diff` after being written
- **THEN** the only files added or modified SHALL be under `openspec/changes/dynamic-playbook-parameter-binding/`, with zero changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.

#### Scenario: No playbook rows created
- **WHEN** this change's artifacts are created
- **THEN** no `playbook_definitions` row SHALL be created and no existing engine behavior SHALL be modified — implementation remains a separate, later pass.
