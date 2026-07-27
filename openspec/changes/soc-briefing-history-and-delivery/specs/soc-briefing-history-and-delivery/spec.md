## ADDED Requirements

### Requirement: Durable briefing history API
The system SHALL expose briefing history from persisted SIEM briefing records without requiring Slack delivery or new investigation execution.

#### Scenario: List saved briefings
- **WHEN** an authorized analyst requests briefing history
- **THEN** the API SHALL return paginated briefing records with briefing id, schedule/window metadata, generated time, content status, run status, provider status, delivery status summary, and concise summary text
- **AND** it SHALL NOT trigger investigation, AI synthesis, Slack delivery, or production mutation

#### Scenario: Filter and search briefing history
- **WHEN** the request includes status, schedule, date range, delivery status, provider/degraded status, or search filters
- **THEN** the API SHALL apply bounded PostgreSQL-backed filtering and pagination
- **AND** it SHALL enforce maximum page size and stable ordering

### Requirement: Briefing detail API
The system SHALL expose a bounded briefing detail API that returns structured sections, evidence references, lifecycle status, delivery attempts, and run metadata for one saved briefing.

#### Scenario: Read briefing detail
- **WHEN** an authorized analyst opens a briefing detail
- **THEN** the API SHALL return structured sections for `alerts_reviewed`, `dismissed_low_priority_findings`, `escalations`, `critical_findings`, `evidence`, and `recommendations`
- **AND** it SHALL include evidence references and concise run-step summaries without returning hidden chain-of-thought or unbounded raw evidence

#### Scenario: Missing briefing is safe
- **WHEN** a requested briefing id does not exist
- **THEN** the API SHALL return a not-found response without leaking unrelated schedule, run, or delivery data

### Requirement: Analyst briefing history UI
The frontend SHALL provide a SIEM briefing history workspace or panel for browsing and reading saved briefings.

#### Scenario: Browse briefing history
- **WHEN** an analyst opens the briefing history workspace
- **THEN** the UI SHALL show a dense operational list with search, filters, pagination, content lifecycle, run status, generated time/window, and delivery status
- **AND** the first screen SHALL be the usable history experience rather than a marketing or explanatory page

#### Scenario: Present structured briefing detail
- **WHEN** an analyst selects a briefing
- **THEN** the UI SHALL present the saved structured sections, recommendations, evidence references, degraded-state errors, and delivery attempts in a readable read-only detail view
- **AND** it SHALL distinguish briefing content status from Slack delivery status

### Requirement: RBAC and read-only behavior
The system SHALL enforce RBAC for briefing history and delivery controls. Briefing browsing SHALL be read-only with respect to alerts, incidents, notes, SOAR, approvals, notification policy, and production data.

#### Scenario: Analyst can read briefings
- **WHEN** a user with analyst or super-admin privileges requests briefing history or detail
- **THEN** the system SHALL allow the read operation according to existing session/RBAC patterns

#### Scenario: Unauthorized user is blocked
- **WHEN** a viewer or unauthenticated user requests briefing history, detail, or delivery retry controls
- **THEN** the system SHALL deny the request consistently with existing RBAC behavior

#### Scenario: Briefing UI cannot mutate SOC entities
- **WHEN** an analyst uses briefing history or detail screens
- **THEN** the UI SHALL NOT expose controls that approve/deny work, execute SOAR, mutate incidents, write notes, change blocklists, configure providers, or deploy code

### Requirement: Optional Slack summary delivery
The system SHALL support optional Slack summary delivery for saved briefings when notification policy and Slack readiness allow it. Slack delivery SHALL NOT be required for successful briefing persistence.

#### Scenario: Slack disabled skips delivery
- **WHEN** Slack delivery is disabled or not ready
- **THEN** the system SHALL persist delivery status `skipped` or `blocked` with a clear reason
- **AND** the saved briefing SHALL remain available and retain its original content lifecycle status

#### Scenario: Slack summary sends sanitized content
- **WHEN** Slack delivery is enabled and a briefing is ready
- **THEN** the system SHALL send only a concise sanitized summary with generated time/window, top-level findings, recommendations, and a SIEM link or direction
- **AND** it SHALL NOT send raw evidence rows, secrets, hidden chain-of-thought, provider prompts, or unbounded internal details

### Requirement: Delivery status tracking and retries
The system SHALL persist delivery lifecycle records with idempotency, attempt counts, timestamps, provider/channel metadata, next retry time, failure codes, and final outcomes.

#### Scenario: Duplicate delivery is prevented
- **WHEN** workers, retries, or manual controls attempt to deliver the same briefing summary more than once
- **THEN** a deterministic delivery idempotency key SHALL prevent duplicate Slack messages
- **AND** duplicate attempts SHALL reuse or record the existing delivery state

#### Scenario: Delivery retries are bounded
- **WHEN** Slack delivery fails with a retryable error
- **THEN** the system SHALL schedule bounded retry/backoff metadata and increment attempt count
- **AND** retries SHALL stop at the configured maximum attempts with final status `failed`

#### Scenario: Slack failure does not invalidate briefing
- **WHEN** Slack delivery fails or exhausts retries
- **THEN** the delivery record SHALL show failure details
- **AND** the saved briefing SHALL remain readable and SHALL NOT be marked failed solely because delivery failed

### Requirement: Audit logging
The system SHALL audit briefing history access where appropriate, delivery enqueue/send/retry/failure outcomes, duplicate suppression, and administrative delivery controls using sanitized metadata.

#### Scenario: Delivery audit is attributed
- **WHEN** Slack delivery is skipped, sent, retried, blocked, duplicate-suppressed, or failed
- **THEN** the audit log SHALL include briefing id, delivery channel, status, sanitized reason, timing metadata, actor/service identity, and idempotency key
- **AND** it SHALL NOT store secrets, webhook URLs, raw Slack payload secrets, or hidden chain-of-thought

### Requirement: Degraded and offline state visibility
The system SHALL preserve and display degraded briefing states caused by disabled gateway, provider unavailable, provider timeout, partial evidence, budget exhaustion, worker crash, or delivery outage.

#### Scenario: Degraded briefing remains visible
- **WHEN** a briefing has status `partial`, `blocked`, `failed`, or provider unavailable metadata
- **THEN** list and detail APIs SHALL expose the status and concise error metadata
- **AND** the UI SHALL present the degraded state without implying that a production action occurred

### Requirement: Retention expectations
The system SHALL document and expose retention expectations for briefing, run-step, evidence reference, delivery, and audit records.

#### Scenario: Retention does not silently delete history
- **WHEN** briefing history is displayed
- **THEN** the system SHALL preserve historical records according to configured retention expectations
- **AND** any future destructive cleanup SHALL require a separate explicit retention job or approved change
