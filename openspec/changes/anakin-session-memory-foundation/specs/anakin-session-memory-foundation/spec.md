## ADDED Requirements

### Requirement: Private durable thread identity
The system SHALL persist SIEM conversation threads privately per owner and SHALL idempotently resolve one active default thread per owner, domain, and investigation/entity scope while permitting intentionally created non-default threads.

#### Scenario: Default thread is idempotent
- **WHEN** the same owner concurrently or repeatedly requests a default thread for the same accessible scope
- **THEN** exactly one active default thread SHALL exist and each successful response SHALL identify that thread.

#### Scenario: Explicit thread is separate
- **WHEN** an owner intentionally requests a non-default thread for an accessible scope
- **THEN** the system SHALL create a separate private thread without changing the default identity.

#### Scenario: Other owner cannot enumerate thread
- **WHEN** another authenticated user requests or mutates a thread they do not own
- **THEN** the system SHALL return a non-enumerating not-found or forbidden response without disclosing thread content or existence.

### Requirement: Ordered idempotent turns
The system SHALL allocate immutable turn sequences transactionally, require `client_request_id`, and enforce optimistic thread versions for writes.

#### Scenario: Turn append advances sequence and version
- **WHEN** an owner submits a valid turn with the current expected version
- **THEN** the system SHALL append the next unique sequence and atomically advance thread sequence, version, activity, and retention timestamps.

#### Scenario: Duplicate request returns original turn
- **WHEN** the same owner retries a turn with the same thread and `client_request_id`
- **THEN** the system SHALL return the original turn/request without allocating a new sequence or changing thread version.

#### Scenario: Stale concurrent write conflicts
- **WHEN** two submissions use the same expected version and one commits first
- **THEN** the later non-duplicate submission SHALL receive an explicit conflict and SHALL NOT create a turn.

#### Scenario: Out-of-order completion cannot overwrite state
- **WHEN** an async operation is linked to an ordered turn
- **THEN** database linkage and optimistic version checks SHALL prevent completion against another owner, thread, turn, or newer state.

### Requirement: Provenance-separated investigation state
The system SHALL distinguish verified evidence, analyst statements, model inferences, corrections, and unresolved questions in normalized storage.

#### Scenario: Unsupported claim remains analyst statement
- **WHEN** a user submits an unsupported claim
- **THEN** it SHALL be stored as `analyst_statement` and SHALL NOT create verified evidence.

#### Scenario: Model conclusion remains inference
- **WHEN** a trusted backend component stores a model conclusion or hypothesis
- **THEN** it SHALL use `model_inference` provenance with confidence and SHALL NOT be represented as verified evidence.

#### Scenario: Correction supersedes inference only
- **WHEN** an analyst correction targets a prior model inference or analyst statement
- **THEN** the system SHALL preserve both records and identify the supersession
- **AND** SHALL reject attempts to overwrite or supersede a verified evidence record.

#### Scenario: Malformed state is not trusted
- **WHEN** structured state fails schema, type, depth, or size validation
- **THEN** the system SHALL reject the write or return a safe rebuild-required state without treating malformed data as authoritative.

### Requirement: Bounded evidence and entity associations
The system SHALL store owner-scoped typed entities and bounded sanitized evidence references with source, observation, freshness, relationship, fingerprint, and provenance metadata.

#### Scenario: Evidence snapshot is bounded and sanitized
- **WHEN** verified evidence is stored
- **THEN** secret-bearing values SHALL be redacted, oversized or deeply nested content SHALL be rejected or bounded, and provenance SHALL remain `verified_evidence`.

#### Scenario: Deleted or inaccessible target is not substituted
- **WHEN** a thread's investigation or entity is deleted or no longer accessible
- **THEN** new mutation SHALL fail explicitly and SHALL NOT select another investigation or entity.

### Requirement: Retention, expiry, reset, and deletion
The system SHALL expire active context after seven days of inactivity, retain closed content until 90 days after activity, and then support hard deletion while retaining only minimal non-content tombstone metadata.

#### Scenario: Expired thread is excluded
- **WHEN** a thread passes its inactivity expiry
- **THEN** reads requiring active context or all mutations SHALL return `410`
- **AND** its content SHALL be ineligible for future prompt context.

#### Scenario: Reset creates clean replacement
- **WHEN** an owner resets an active default thread with the current version
- **THEN** the old thread SHALL close immediately and reject future mutation
- **AND** a fresh default thread with no inherited turns or state SHALL be created transactionally.

#### Scenario: Reset races with append
- **WHEN** reset and turn submission race on the same thread
- **THEN** row locking and version checks SHALL establish one order and the losing stale operation SHALL not mutate closed or superseded state.

#### Scenario: Due content is hard-deleted
- **WHEN** a bounded retention sweep processes a thread at or beyond `delete_after`
- **THEN** thread content and dependent records SHALL be deleted by cascade
- **AND** only non-sensitive tombstone metadata SHALL remain.

### Requirement: Artifact preview continuity
The system SHALL permit sanitized generated-artifact text to survive refresh as a conversation turn while preserving review-only safety.

#### Scenario: Artifact preview labels are mandatory
- **WHEN** an artifact preview turn is stored
- **THEN** it SHALL have `preview_only=true`, `persisted=false`, `applied=false`, and `approval_required=true`
- **AND** no API in this capability SHALL confirm, apply, or save it as an operational SIEM record.

### Requirement: Foundation API and RBAC
The system SHALL expose authenticated create/read/reset/thread-turn APIs for currently active analysts and super-admins without invoking an LLM.

#### Scenario: Foundation API lifecycle
- **WHEN** an authorized owner creates or reads a thread, lists cursor-paginated turns, submits a foundation turn, or resets a thread
- **THEN** the API SHALL enforce ownership, current role, lifecycle, target access, expected version, idempotency, sanitization, and bounded pagination.

#### Scenario: Disabled or downgraded user is denied
- **WHEN** a user's current account is disabled or no longer has analyst/super-admin role
- **THEN** every foundation request SHALL be denied based on current authentication state rather than a queued role snapshot.

#### Scenario: Namespace boundaries are preserved
- **WHEN** a request attempts to create Repo Assistant or SOC Briefing state through the SIEM thread API
- **THEN** it SHALL be rejected without mixing namespaces or continuing those workflows.

### Requirement: Existing safety boundaries remain unchanged
The foundation SHALL NOT alter model routing, paid-fallback policy, Decision Support mutation guarantees, Generate Artifact apply behavior, Analyst Workspace records, existing async execution, Repo Assistant, SOC Briefing, or frontend behavior.

#### Scenario: Foundation turn does not execute AI
- **WHEN** a valid turn is persisted through this phase's API
- **THEN** no model, tool, workflow worker, artifact apply path, or Analyst Workspace mutation SHALL execute.
