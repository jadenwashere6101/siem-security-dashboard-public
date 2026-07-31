## ADDED Requirements

### Requirement: Manual-first SOC briefing mode
The system SHALL expose a SOC briefing operating mode with `manual_only` and `scheduled_autonomous` values. Manual runs SHALL remain available in either mode, while `manual_only` SHALL prevent autonomous schedules from enqueueing new jobs.

#### Scenario: Manual-only blocks autonomous enqueueing
- **WHEN** the briefing mode is `manual_only` and the scheduled briefing worker checks due schedules
- **THEN** the worker SHALL NOT materialize new schedule windows or jobs for autonomous schedules
- **AND** it SHALL report a clear skipped or blocked scheduling outcome without disabling saved schedules.

#### Scenario: Scheduled autonomous preserves catch-up
- **WHEN** the briefing mode is `scheduled_autonomous`
- **THEN** enabled schedules SHALL use the existing bounded catch-up behavior
- **AND** missed windows SHALL remain bounded by existing catch-up count, lookback, and coalescing policy.

### Requirement: Run Anakin Briefing Now
The system SHALL allow an authenticated analyst or super-admin to request one bounded manual SOC briefing run through the existing worker job path.

#### Scenario: Analyst starts a manual briefing
- **WHEN** an analyst clicks "Run Anakin Briefing Now"
- **THEN** the backend SHALL create exactly one pending manual briefing job using existing schedule, window, job, run, and briefing persistence contracts
- **AND** the job SHALL be marked with safe manual trigger metadata.

#### Scenario: Manual run persists to history
- **WHEN** the worker processes a manual briefing job successfully or partially
- **THEN** the resulting briefing SHALL be saved in existing SOC briefing history
- **AND** list/detail APIs SHALL distinguish it as manually triggered.

### Requirement: Duplicate manual run prevention
The system SHALL prevent repeated run-now clicks from creating duplicate active manual briefing work.

#### Scenario: Active manual job already exists
- **WHEN** an analyst requests Run Now while a manual briefing job is pending or running
- **THEN** the API SHALL return the existing active job status
- **AND** it SHALL NOT create another pending or running manual job.

### Requirement: Pause schedules without blocking manual runs
The system SHALL expose a pause schedules control that stops autonomous schedule materialization without disabling manual runs.

#### Scenario: Pause blocks schedules
- **WHEN** schedules are paused
- **THEN** the worker SHALL NOT enqueue new autonomous scheduled jobs
- **AND** the status API SHALL show schedules as paused.

#### Scenario: Pause does not block manual run
- **WHEN** schedules are paused and an analyst requests Run Now
- **THEN** the system SHALL still create or return one bounded manual job according to duplicate-prevention rules.

### Requirement: Briefing control status
The system SHALL expose status for last successful run, next scheduled run, catch-up policy/status, local model status, local-only mode, and no-paid-fallback state.

#### Scenario: Status shows local-only AI state
- **WHEN** the status API is requested
- **THEN** it SHALL report AI Gateway mode, local provider/model readiness, whether local provider is configured, and whether paid fallback is disabled
- **AND** it SHALL NOT expose secrets, webhook URLs, prompts, or provider credentials.

#### Scenario: Status shows schedule state
- **WHEN** schedules exist
- **THEN** the status API SHALL report next scheduled run, catch-up settings, pause state, pending/running job counts, and last successful run where available.

### Requirement: SOC Briefings UI controls
The frontend SHALL expose analyst-visible mode, pause, run-now, schedule, catch-up, model, and no-paid-fallback controls/status in the SOC Briefings workspace.

#### Scenario: Analyst sees manual-first controls
- **WHEN** an analyst opens SOC Briefings
- **THEN** the first visible panel SHALL include "Run Anakin Briefing Now", mode selection, pause schedules, last successful run, next scheduled run, catch-up status, local model status, and no-paid-fallback indicator.

#### Scenario: Run-now feedback is clear
- **WHEN** a run-now request succeeds, returns an existing active job, is blocked, or fails
- **THEN** the UI SHALL show clear loading, success, already-running, blocked/unavailable, or failure feedback without implying a production action occurred.

### Requirement: RBAC, audit, and read-only boundaries
Manual briefing controls SHALL preserve existing SOC briefing RBAC, audit, and read-only advisory boundaries.

#### Scenario: Viewer cannot control briefings
- **WHEN** a viewer or unauthenticated user requests status changes or run-now
- **THEN** the system SHALL deny the request consistently with existing RBAC behavior.

#### Scenario: No production mutation path is introduced
- **WHEN** mode changes, pause changes, status reads, or manual briefing jobs are requested
- **THEN** the system SHALL NOT approve, deny, execute SOAR, mutate incidents, write notes, change blocklists, run shell/file/subprocess code, deploy code, or enable paid fallback.
