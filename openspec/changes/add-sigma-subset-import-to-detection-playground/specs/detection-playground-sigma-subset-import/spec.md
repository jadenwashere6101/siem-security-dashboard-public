## ADDED Requirements

### Requirement: Sigma subset import uses the existing rollback-safe playground evaluator
The Detection Playground SHALL accept a Sigma YAML simulation mode that compiles analyst-supplied Sigma rules into the bounded internal playground rule model and executes them only through the existing temporary-rule simulator path. The system SHALL NOT create a second detection engine, SHALL NOT execute raw Sigma semantics directly against production tables, and SHALL preserve the existing rollback-only transaction, pasted-event-only evaluation, zero-durable-write guarantees, alert preview, MITRE preview, SOAR preview, explainability, and pipeline visualization contracts.

#### Scenario: Sigma simulation reuses the temporary-rule path
- **WHEN** an authorized analyst submits a supported Sigma rule and pasted events for simulation
- **THEN** the backend compiles the Sigma rule into the internal playground rule model and executes it through the existing rollback-safe simulator path only

#### Scenario: Unsupported alternate execution path is absent
- **WHEN** a Sigma simulation request is processed
- **THEN** no second evaluator, no production-rule creation path, and no direct production-table query path is invoked

### Requirement: Sigma YAML parsing is safe and fail-closed
The backend SHALL parse Sigma input only with a safe YAML parser and SHALL reject malformed or oversized YAML before compilation. The parser SHALL accept only the bounded request shape required for Version 3 Sigma subset import and SHALL reject unsupported YAML constructs with explicit validation errors.

#### Scenario: Malformed YAML is rejected
- **WHEN** the submitted Sigma text is not valid YAML
- **THEN** the backend rejects the request before compilation and returns a structured parse error

#### Scenario: Oversized or unbounded YAML is rejected
- **WHEN** the submitted Sigma text exceeds configured request, depth, or structural limits
- **THEN** the backend rejects the request before field mapping or simulation

### Requirement: Version 3 supports a strict Sigma subset only
Version 3 SHALL support only this Sigma subset: metadata fields `title`, `id`, `status`, `description`, `author`, and `date`; `logsource` when it maps cleanly to one canonical source; `level`; `tags` including supported ATT&CK tags; `detection` selections using exact matches, lists of values, and safe string modifiers `contains`, `startswith`, and `endswith`; and `condition` expressions composed from named selections using simple `and`, `or`, and `not`.

#### Scenario: Supported Sigma rule is accepted
- **WHEN** a Sigma rule uses only supported metadata, supported logsource mapping, supported field mappings, supported selection values, and a simple boolean condition over named selections
- **THEN** the backend accepts the rule for compilation and simulation

#### Scenario: Supported list values are accepted
- **WHEN** a Sigma selection uses a supported field with a list of exact-match values
- **THEN** the backend compiles that selection into the internal rule model without expanding its scope beyond the provided list

### Requirement: Unsupported Sigma constructs fail with explicit errors
The backend SHALL reject unsupported Sigma constructs with explicit validation errors and SHALL NOT silently drop, broaden, or reinterpret them. Rejected constructs SHALL include regex, wildcard selection expansion, Sigma correlation rules, Sigma aggregation syntax, unsupported modifiers, backend-specific Sigma extensions, ambiguous logsource mappings, and unsupported or unmappable fields.

#### Scenario: Unsupported modifier is rejected
- **WHEN** a Sigma selection uses an unsupported modifier such as `re`, `cidr`, `base64`, `all`, or another unapproved modifier
- **THEN** the backend rejects the rule with an error that identifies the field and unsupported modifier

#### Scenario: Wildcard selection expansion is rejected
- **WHEN** a Sigma condition uses constructs such as `1 of`, `all of`, or wildcard selection names
- **THEN** the backend rejects the rule with an explicit unsupported-condition error

#### Scenario: Correlation or aggregation syntax is rejected
- **WHEN** a Sigma rule uses correlation-rule or aggregation/timeframe syntax
- **THEN** the backend rejects the rule instead of attempting partial execution

### Requirement: Logsource mapping must resolve to one canonical source
The backend SHALL map Sigma `logsource` input only when it resolves unambiguously to one of this SIEM's six canonical sources: `honeypot`, `bank_app`, `pfsense`, `nginx`, `azure_insights`, or `opentelemetry`. The response SHALL identify the resolved canonical `source` and `source_type` in the normalized internal-rule preview.

#### Scenario: Unambiguous logsource is mapped
- **WHEN** a supported Sigma `logsource` maps cleanly to one canonical source
- **THEN** the backend resolves the canonical `source` and `source_type` and includes them in the normalized internal-rule preview

#### Scenario: Ambiguous logsource is rejected
- **WHEN** a Sigma `logsource` could correspond to more than one canonical source or lacks enough information to choose safely
- **THEN** the backend rejects the rule with an ambiguity error rather than guessing

### Requirement: Field mapping is explicit and source-aware
The backend SHALL map Sigma fields into this SIEM's normalized schema using validator-owned, source-aware mapping tables. Supported mappings SHALL include approved aliases for normalized fields such as `source_ip`, `destination_ip`, `destination_port`, `username`, `event_type`, `event_outcome`, `http_status`, `action`, and `severity`. The system SHALL never silently remap unsupported fields.

#### Scenario: Supported alias maps to a normalized field
- **WHEN** a Sigma selection uses an approved field alias for the resolved canonical source
- **THEN** the backend maps that alias to the corresponding normalized field in the internal-rule preview

#### Scenario: Unsupported field is rejected
- **WHEN** a Sigma selection uses a field that is not supported for the resolved canonical source
- **THEN** the backend rejects the rule with an error that identifies the original field and explains that no safe mapping exists

### Requirement: Mapping failures explain why compilation stopped
Analyst-facing Sigma validation errors SHALL explain whether failure was caused by an unknown field, ambiguous logsource, unsupported field for the resolved source, unsupported modifier, or unsupported condition syntax. Error payloads SHALL identify the original Sigma element that failed and SHALL NOT fabricate a fallback mapping.

#### Scenario: Analyst sees mapping failure details
- **WHEN** Sigma compilation fails due to a field or logsource mapping problem
- **THEN** the response includes structured validation details describing the failed Sigma element, the failure class, and the reason compilation stopped

### Requirement: Sigma rules compile into a minimally expanded internal playground rule model
The backend SHALL compile supported Sigma rules into the existing bounded internal playground rule model with only the minimum expansion required for Version 3: a bounded predicate tree supporting `all`, `any`, and `not` boolean composition over leaf predicates; metadata fields for Sigma preview; and the existing canonical-source, severity, and preview-safe execution fields. The backend SHALL NOT compile Sigma into a general-purpose programming or query language.

#### Scenario: Simple boolean selections compile successfully
- **WHEN** a supported Sigma condition combines named selections with simple `and`, `or`, and `not`
- **THEN** the backend emits a bounded internal predicate tree in the normalized internal-rule preview and executes that compiled form through the existing evaluator

#### Scenario: Compilation stays minimal
- **WHEN** a supported Sigma rule is compiled
- **THEN** the resulting internal rule object contains only the bounded predicate structure and preview metadata required for simulation

### Requirement: Sigma simulation remains pasted-event-only and preview-only
Sigma simulations SHALL evaluate only the pasted or sample events included in the current request and SHALL remain preview-only. They SHALL NOT read committed production history for threshold or dedup semantics, SHALL NOT persist imported Sigma rules, SHALL NOT modify production detection rules, SHALL NOT create worker-visible rows, and SHALL NOT call external integrations or third-party APIs.

#### Scenario: Sigma simulation uses request-scoped events only
- **WHEN** a Sigma simulation rule is evaluated
- **THEN** only the pasted or sample events in that request contribute to the result

#### Scenario: No persistence or side effects occur
- **WHEN** a Sigma simulation reaches alert, MITRE, or SOAR preview stages
- **THEN** no durable row is committed, no production rule is modified, and no external integration is executed

### Requirement: Sigma mode reuses existing pipeline, explainability, and rollback disclosure
The Detection Simulator UI SHALL add a Sigma YAML mode that reuses the existing results layout, pipeline visualization, explainability surface, alert preview, MITRE preview, SOAR preview, and rollback/non-persistence disclosure. The frontend SHALL render backend-authored validation, mapping, compilation, and simulation evidence only and SHALL NOT perform Sigma evaluation client-side.

#### Scenario: Sigma mode shows normalized internal-rule preview
- **WHEN** the analyst enters a supported Sigma rule
- **THEN** the UI displays backend-authored validation feedback and a normalized internal-rule preview before or alongside simulation results

#### Scenario: Existing simulator presentation remains consistent
- **WHEN** the analyst switches between production-rule, temporary-rule, and Sigma modes
- **THEN** the shared pipeline and explainability surfaces remain structurally consistent while clearly labeling Sigma subset semantics

### Requirement: Version 3 requires focused Sigma verification without changing existing modes
Implementation of Sigma subset import SHALL include focused backend and frontend tests for valid Sigma rules, malformed YAML, unsupported constructs, logsource mapping, field alias mapping, ATT&CK tag handling, internal compilation, rollback safety, zero durable writes, Version 1 regression protection, Version 2 regression protection, frontend validation feedback, accessibility, browser verification, and frontend production build success.

#### Scenario: Existing modes remain unchanged
- **WHEN** Sigma subset import is implemented
- **THEN** existing Version 1 production-rule simulation and existing Version 2 temporary-rule simulation continue to behave as they do today

#### Scenario: No migration is required by default
- **WHEN** implementation completes without discovering a hard blocker
- **THEN** the feature ships with no schema migration and the verification record states that expectation explicitly
