## ADDED Requirements

### Requirement: Numeric planner token usage remains observable

The session-memory sanitizer SHALL preserve `prompt_tokens` and `completion_tokens` as unchanged numeric values when they are non-negative integers, including within nested structured metadata that satisfies existing depth and size limits.

#### Scenario: Safe token counts are sanitized
- **WHEN** structured session metadata contains numeric `prompt_tokens` and `completion_tokens`
- **THEN** both fields remain numeric and unchanged after sanitization

#### Scenario: Safe token counts are nested
- **WHEN** approved numeric token-count fields appear inside a supported nested planner-attempt structure
- **THEN** the fields remain numeric without changing the existing session-memory depth contract

### Requirement: Credential redaction remains fail-closed

The session-memory sanitizer MUST continue to redact passwords, secrets, API keys, authorization data, credential-bearing token fields, and every token-bearing field not explicitly approved as numeric usage telemetry. An approved token-count key with a non-numeric, negative, or boolean value MUST remain redacted.

#### Scenario: Known credential token fields are redacted
- **WHEN** structured metadata contains access, refresh, API, bearer, session, or authentication token fields
- **THEN** their values are replaced by the existing redaction marker

#### Scenario: Unknown token field is redacted
- **WHEN** structured metadata contains an unclassified key whose name includes `token`
- **THEN** its value is replaced by the existing redaction marker

#### Scenario: Existing secret categories are redacted
- **WHEN** structured metadata contains API keys, secrets, passwords, or nested credential tokens
- **THEN** those values remain redacted recursively

### Requirement: Planner reliability metadata persists without unsafe content

The system SHALL persist bounded planner reliability metadata containing available prompt and completion token counts, completion state, stop reason, and typed validation stage, code, and path. It MUST NOT persist raw prompts, raw failed plans, hidden reasoning, secrets, or credentials as part of this metadata.

#### Scenario: Planner metadata is persisted safely
- **WHEN** a controlled planner attempt is stored with token counts, completion metadata, and validation results
- **THEN** the safe fields remain available and raw or secret-bearing diagnostic content is absent or redacted

### Requirement: Existing session-memory boundaries remain unchanged

This capability SHALL NOT alter provider routing, accounting, planner decisions, prompts, RBAC, AI workflows, session-memory depth validation, or artifact normalization behavior.

#### Scenario: Existing boundary regressions run
- **WHEN** affected session-memory, conversation orchestration, artifact normalization, provider, and accounting regressions execute
- **THEN** their behavior remains unchanged except for preservation of the two approved numeric usage fields
