## ADDED Requirements

### Requirement: Scheduled investigation lifecycle
The system SHALL run read-only autonomous investigations only from a claimed scheduled SOC briefing job with an isolated run created by the scheduled briefing runtime.

#### Scenario: Claimed job starts investigation engine
- **WHEN** the scheduled briefing worker claims a runnable job and creates an isolated run
- **THEN** it SHALL invoke the read-only investigation engine for that run
- **AND** the engine SHALL persist run-step records for planning, evidence collection, AI synthesis, briefing persistence, and finalization

#### Scenario: Investigation does not create runtime work
- **WHEN** the investigation engine starts
- **THEN** it SHALL NOT materialize schedules, create schedule windows, claim jobs, renew non-owned leases, or run inside Flask/Gunicorn

### Requirement: Deterministic read-only investigation planning
The system SHALL build investigation plans deterministically before any AI provider call. Plans SHALL cover bounded candidates from new alerts, incidents, recon activity, monitored indicators, response registry records, source IP context, and related evidence.

#### Scenario: Plan uses bounded candidates
- **WHEN** a schedule window is investigated
- **THEN** the planner SHALL select no more than the configured maximum entities per run
- **AND** it SHALL record skipped candidates with concise reasons such as `entity_limit_exceeded`, `outside_window`, `duplicate_recent_investigation`, or `unsupported_entity_type`

#### Scenario: Model cannot plan tools
- **WHEN** a provider response contains requested tool calls, SQL, shell commands, file paths, or production actions
- **THEN** the engine SHALL treat that content as invalid advisory text
- **AND** it SHALL NOT execute those requests

### Requirement: SOC read-tool evidence collection
The system SHALL collect evidence only through existing approved SOC read tools and the local SOC tool executor. Tool names, arguments, roles, pagination, row limits, and redaction SHALL be validated before each call.

#### Scenario: Approved tool call is recorded
- **WHEN** the engine executes a SOC read tool
- **THEN** it SHALL persist a run-step record with the approved tool identifier, sanitized input, evidence references, status, timing, truncation metadata, and errors when present
- **AND** the step SHALL identify the work as read-only

#### Scenario: Unsupported or mutation-like tool is rejected
- **WHEN** a planned tool name is unsupported or has mutation intent
- **THEN** validation SHALL reject the call before execution
- **AND** the run SHALL persist a failed or skipped step with a clear failure code

### Requirement: Hard investigation budgets
The system SHALL enforce hard maximums for runtime, tool calls, candidate entities, evidence references, evidence bytes or characters, prompt tokens, completion tokens, and estimated cost.

#### Scenario: Tool budget is exhausted
- **WHEN** the planned evidence collection exceeds the maximum tool-call budget
- **THEN** the engine SHALL execute no more than the configured maximum
- **AND** omitted work SHALL be recorded with status `partial` or failure code `budget_exhausted`

#### Scenario: Prompt budget compacts evidence
- **WHEN** collected evidence exceeds the AI prompt evidence budget
- **THEN** the engine SHALL compact evidence to sanitized summaries and references
- **AND** it SHALL NOT include unbounded raw rows in the prompt or briefing content

### Requirement: Investigation deduplication
The system SHALL avoid re-investigating the same work unnecessarily using deterministic deduplication keys for schedule windows, entity identity, normalized indicators, evidence fingerprints, and investigation profile.

#### Scenario: Recent duplicate is skipped
- **WHEN** an entity or evidence bundle has already been successfully or partially investigated within the configured deduplication horizon
- **THEN** the engine SHALL skip duplicate collection for that entity
- **AND** it SHALL persist a skipped step or result with reason `duplicate_recent_investigation`

#### Scenario: New evidence bypasses duplicate suppression
- **WHEN** an entity has new material evidence after the previous investigation fingerprint
- **THEN** the engine SHALL allow a new read-only investigation within budget
- **AND** it SHALL link the result to the new evidence references

### Requirement: AI Gateway synthesis flow
The system SHALL use the existing AI Gateway only to synthesize structured advisory briefing content from bounded sanitized evidence. The provider SHALL NOT receive database handles, tool dispatch handles, shell/file access, approval callbacks, or raw secret-bearing prompts.

#### Scenario: Gateway disabled is persisted
- **WHEN** AI Gateway mode is disabled or invalid before synthesis
- **THEN** the run SHALL persist status `blocked` or `partial` with a clear gateway failure code
- **AND** deterministic evidence collection results SHALL remain durable

#### Scenario: Local provider unavailable
- **WHEN** local-only provider readiness fails, times out, or returns unavailable
- **THEN** the engine SHALL persist an unavailable or timeout outcome
- **AND** it SHALL NOT spend on paid fallback unless a future explicit policy enables scheduled paid fallback

#### Scenario: Provider output must match schema
- **WHEN** the provider returns briefing content
- **THEN** the engine SHALL parse and validate it against the structured briefing schema
- **AND** invalid or malformed output SHALL produce a failed or partial synthesis step without losing collected evidence

### Requirement: Structured advisory briefing content
The system SHALL persist structured briefing content in the SIEM briefing lifecycle records without requiring frontend UI changes. Briefings SHALL include consistent advisory sections and source references.

#### Scenario: Successful briefing content is saved
- **WHEN** evidence collection and synthesis complete successfully
- **THEN** `soc_briefings` SHALL store sections for `alerts_reviewed`, `dismissed_low_priority_findings`, `escalations`, `critical_findings`, `evidence`, and `recommendations`
- **AND** recommendations SHALL be advisory and source-referenced

#### Scenario: Partial briefing is saved
- **WHEN** some evidence or synthesis steps fail after durable evidence was collected
- **THEN** the system SHALL persist a partial briefing with available sections, omitted counts, failure codes, and evidence references
- **AND** it SHALL NOT mark the run as silently successful

### Requirement: Completion states and failure handling
The system SHALL persist explicit investigation completion states including `successful`, `partial`, `skipped`, `blocked`, `failed`, `provider_unavailable`, `provider_timeout`, `budget_exhausted`, and `persistence_failed`.

#### Scenario: Persistence failure aborts active job
- **WHEN** required run, run-step, audit, or briefing persistence fails
- **THEN** the worker SHALL stop processing the active job
- **AND** it SHALL surface the failure through logs and durable state where possible instead of continuing silently

#### Scenario: Worker crash preserves recovery path
- **WHEN** the worker crashes during investigation
- **THEN** the phase-one lease recovery mechanism SHALL recover or fail the job according to retry limits
- **AND** already persisted run steps SHALL remain associated with the isolated run

### Requirement: Audit logging for scheduled investigations
The system SHALL audit scheduled investigation activity with sanitized inputs, tool identifiers, evidence references, outcomes, timing, errors, service actor attribution, and concise decision summaries.

#### Scenario: Tool audit uses service actor
- **WHEN** a scheduled investigation executes or skips a tool call
- **THEN** audit metadata SHALL attribute the action to `scheduled_soc_briefing_worker`
- **AND** it SHALL NOT store hidden chain-of-thought, raw secrets, or unnecessary raw evidence payloads

### Requirement: Read-only security boundaries
The investigation engine SHALL preserve all existing production-action boundaries. It SHALL NOT perform model-generated SQL, direct model database access, provider-side tool execution, prompt-to-action execution, SOAR execution, approval decisions, incident or note mutations, Slack delivery, shell/file/subprocess/eval/exec, commits, pushes, deployments, or automatic paid-provider spending.

#### Scenario: Production mutation path is absent
- **WHEN** the scheduled investigation engine runs end-to-end
- **THEN** no approval, SOAR action, notification, incident mutation, note write, blocklist change, database migration, deployment, shell command, or file operation SHALL be performed from model output or investigation decisions
- **AND** any attempted mutation-like operation SHALL fail closed with a durable failed or blocked step
