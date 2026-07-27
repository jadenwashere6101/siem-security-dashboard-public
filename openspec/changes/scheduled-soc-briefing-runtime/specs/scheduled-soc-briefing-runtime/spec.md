## ADDED Requirements

### Requirement: Durable scheduled briefing persistence
The system SHALL persist scheduled SOC briefing runtime state in PostgreSQL using additive tables for schedules, schedule windows, queued jobs, investigation runs, run steps, and briefing lifecycle records. The schema SHALL include idempotency keys, status fields, timestamps, sanitized metadata, evidence references, and indexes needed for due-schedule lookup, job claiming, worker health, and briefing lookup.

#### Scenario: Runtime tables preserve schedule and run relationships
- **WHEN** a schedule window is materialized for a schedule
- **THEN** the system SHALL persist a schedule window linked to the schedule
- **AND** the system SHALL persist at most one queued job for that window
- **AND** any run, run step, and briefing lifecycle record SHALL link back to the originating schedule and window

#### Scenario: Migration is additive
- **WHEN** the runtime migration is applied
- **THEN** it SHALL create only additive tables, indexes, constraints, and checks
- **AND** it SHALL NOT alter existing alert, incident, SOAR approval, AI action, notification, or response outcome semantics

### Requirement: Schedule-window idempotency and duplicate prevention
The system SHALL treat each schedule window as the durable idempotency boundary. It SHALL enforce uniqueness for schedule window identity and job idempotency so duplicate timer invocations, worker restarts, or concurrent workers cannot create duplicate jobs for the same schedule window.

#### Scenario: Duplicate window materialization is suppressed
- **WHEN** two workers attempt to materialize the same schedule window concurrently
- **THEN** PostgreSQL uniqueness constraints SHALL allow only one schedule-window row and one job row
- **AND** the duplicate attempt SHALL return the existing window or record a duplicate-suppressed outcome without creating additional work

#### Scenario: Duplicate job key is rejected
- **WHEN** a job insert reuses an existing idempotency key for a schedule window
- **THEN** the system SHALL fail closed or reuse the existing job identity
- **AND** it SHALL NOT create a second runnable job for that window

### Requirement: Systemd-managed worker outside Gunicorn
The scheduled briefing runtime SHALL execute outside Flask and Gunicorn through a repository-owned systemd one-shot service and timer. The runtime SHALL NOT use APScheduler or any in-process Flask/Gunicorn scheduler.

#### Scenario: Timer invokes bounded one-shot worker
- **WHEN** the systemd timer fires
- **THEN** systemd SHALL run a one-shot worker script from the repository virtual environment
- **AND** the worker SHALL process a bounded batch and exit
- **AND** normal web traffic SHALL continue to be served only by the Gunicorn backend service

#### Scenario: Persistent timer wakes after downtime
- **WHEN** the VM is offline during one or more timer windows
- **THEN** `Persistent=true` SHALL cause the timer to wake the worker after boot
- **AND** PostgreSQL catch-up limits SHALL decide how much missed work is created

### Requirement: PostgreSQL job claiming and leases
The worker SHALL claim jobs using PostgreSQL row locking with `FOR UPDATE SKIP LOCKED`, a non-empty lease owner, lease acquisition timestamp, lease heartbeat timestamp, and lease expiration timestamp. Only the lease owner SHALL be allowed to renew or complete a running job.

#### Scenario: Only one worker claims a pending job
- **WHEN** multiple worker instances attempt to claim pending jobs
- **THEN** each pending job SHALL be locked with `FOR UPDATE SKIP LOCKED`
- **AND** at most one worker SHALL transition a job from `pending` to `running`

#### Scenario: Lease owner controls completion
- **WHEN** a worker attempts to complete a running job
- **THEN** the update SHALL match the job id and lease owner
- **AND** a non-owner or expired lease SHALL NOT be allowed to mark the job successful

### Requirement: Bounded batches, runtime, and graceful shutdown
The worker SHALL enforce configurable maximum batch size, maximum materialized windows per run, maximum jobs processed per invocation, maximum wall-clock runtime, and graceful shutdown handling. Exceeding a bound SHALL produce explicit skipped, partial, or failed outcomes rather than continuing indefinitely.

#### Scenario: Batch bound stops additional work
- **WHEN** more due jobs exist than the configured batch size
- **THEN** the worker SHALL claim and process no more than the configured batch size during that invocation
- **AND** remaining jobs SHALL stay pending for a future invocation

#### Scenario: Shutdown preserves recoverable state
- **WHEN** the worker receives SIGTERM during an invocation
- **THEN** it SHALL stop claiming new jobs
- **AND** it SHALL persist completed step outcomes already reached
- **AND** any unfinished leased job SHALL either be marked interrupted or left for stale lease recovery with a clear lease expiration

### Requirement: Stale lease recovery
The runtime SHALL recover expired running job leases in a bounded recovery pass. It SHALL requeue jobs that have attempts remaining and mark jobs failed when retry limits are exhausted.

#### Scenario: Expired lease is requeued
- **WHEN** a running job has an expired lease and attempts remain
- **THEN** the recovery pass SHALL clear lease fields
- **AND** it SHALL transition the job back to `pending`
- **AND** it SHALL increment recovery or attempt metadata with a concise failure reason

#### Scenario: Expired lease exhausts attempts
- **WHEN** a running job has an expired lease and no attempts remain
- **THEN** the recovery pass SHALL clear lease fields
- **AND** it SHALL mark the job `failed` with failure code `stale_lease_expired`

### Requirement: Bounded missed-window catch-up
The scheduler SHALL track `last_successful_window_end` and `next_due_at` for each enabled schedule. It SHALL detect missed windows and create catch-up work only within configured maximum catch-up count and maximum lookback limits.

#### Scenario: Overnight missed work is bounded
- **WHEN** the VM is offline overnight and an enabled schedule misses multiple due windows
- **THEN** the next worker invocation SHALL create no more than the configured maximum catch-up windows
- **AND** it SHALL skip or coalesce older windows with explicit skip reasons
- **AND** it SHALL NOT create an unbounded backlog

#### Scenario: Coalesced catch-up creates one bounded window
- **WHEN** missed windows exceed the configured catch-up count and coalescing is enabled
- **THEN** the scheduler SHALL create one coalesced catch-up window within the maximum lookback
- **AND** skipped windows SHALL be recorded with reason `coalesced` or `outside_lookback`

### Requirement: Explicit schedule validation and skip outcomes
The scheduler SHALL validate schedule cadence, timezone, due timestamps, catch-up limits, and enabled state before creating jobs. Malformed, disabled, stale, or out-of-lookback windows SHALL be persisted or reported with explicit outcomes and SHALL NOT loop silently.

#### Scenario: Malformed schedule fails safely
- **WHEN** a schedule has invalid cadence, timezone, or due-state values
- **THEN** the scheduler SHALL mark the schedule or attempted window as `blocked`
- **AND** it SHALL persist failure code `malformed_schedule`
- **AND** it SHALL NOT enqueue runnable jobs for that schedule until corrected

#### Scenario: Disabled schedule creates no jobs
- **WHEN** a schedule is disabled
- **THEN** the scheduler SHALL NOT materialize new windows or jobs for it
- **AND** existing historical run and briefing records SHALL remain visible to runtime readers

### Requirement: Scheduled read-only service identity
The runtime SHALL execute scheduled work under a fixed service actor, `scheduled_soc_briefing_worker`, with read-only analyst-equivalent SOC tool permissions. The actor SHALL be recorded in jobs, runs, run steps, and audit metadata where applicable.

#### Scenario: Service actor cannot perform production mutations
- **WHEN** scheduled runtime code attempts to invoke an approval decision, incident mutation, note write, SOAR action, Slack delivery, shell command, file access, or other production mutation
- **THEN** the runtime SHALL reject the operation
- **AND** it SHALL persist a failed or blocked step outcome

#### Scenario: Service actor uses existing read-tool validation
- **WHEN** later investigation logic invokes SOC evidence tools from a scheduled run
- **THEN** the call SHALL go through the existing approved read-only SOC tool definitions and validation
- **AND** it SHALL NOT bypass role, argument, row-limit, redaction, or read-only checks

### Requirement: Clear AI and provider availability outcomes
The runtime foundation SHALL persist AI Gateway readiness and unavailable states without requiring model calls for scheduling verification. AI disabled, local provider unavailable, Mini PC unavailable, provider timeout, and paid fallback blocked states SHALL become explicit run or step outcomes.

#### Scenario: AI gateway is disabled
- **WHEN** a scheduled job reaches a phase that requires AI readiness and the gateway mode is disabled
- **THEN** the run SHALL persist status `blocked` or `failed` with failure code `ai_gateway_disabled`
- **AND** it SHALL NOT attempt paid fallback or production actions

#### Scenario: Local provider is unavailable
- **WHEN** local AI readiness reports unavailable, timeout, or provider failure
- **THEN** the run SHALL persist a clear unavailable or timeout outcome
- **AND** the job SHALL complete as blocked, failed, or partial according to the phase reached

### Requirement: Durable run-step records without hidden chain-of-thought
Run-step records SHALL store step type, status, sanitized inputs, approved tool identifiers, evidence references, concise decision summaries, timing, errors, and read-only labels. The system SHALL NOT store hidden model chain-of-thought or raw secret-bearing prompts.

#### Scenario: Step persistence records safe operational evidence
- **WHEN** a runtime step starts, completes, fails, or is skipped
- **THEN** the system SHALL persist a durable step record with sanitized inputs, timing, status, and error metadata
- **AND** any evidence reference SHALL identify source paths or record ids rather than storing unnecessary raw sensitive data

#### Scenario: Persistence failure aborts instead of continuing silently
- **WHEN** a required job, run, run-step, or briefing lifecycle write fails
- **THEN** the worker SHALL roll back the affected transaction where possible
- **AND** it SHALL stop processing that job
- **AND** it SHALL log and surface the persistence failure instead of silently continuing

### Requirement: Worker heartbeat and health visibility
The runtime SHALL persist heartbeat and worker state for the logical `soc_briefing_worker`. Health derivation SHALL distinguish unknown, healthy, degraded, and offline states using persisted heartbeat age and SHALL not depend on queue activity alone.

#### Scenario: Worker heartbeat is updated
- **WHEN** the one-shot worker starts and while it processes bounded work
- **THEN** it SHALL upsert a heartbeat row for `soc_briefing_worker`
- **AND** health readers SHALL expose last heartbeat, started time, build version when available, and concise status text without secrets

#### Scenario: Missing heartbeat is unknown
- **WHEN** no heartbeat has ever been recorded for the briefing worker
- **THEN** runtime health SHALL report `unknown`
- **AND** it SHALL NOT imply that scheduled briefing processing is healthy

### Requirement: Runtime security boundaries
The scheduled briefing runtime SHALL preserve AI and SOC safety boundaries: no model-generated SQL, no direct model database access, no shell, subprocess, file, eval, or exec from model output, no prompt-to-action execution, no production mutation, no automatic paid-provider spending, and no sensitive data sent externally.

#### Scenario: Runtime foundation performs no production action
- **WHEN** the scheduled briefing runtime materializes windows, claims jobs, updates runs, records steps, checks AI readiness, or updates heartbeats
- **THEN** it SHALL NOT approve, deny, execute, retry, resume, abandon, block, unblock, send Slack, create notes, mutate incidents, or deploy code

#### Scenario: Provider cannot access tools directly
- **WHEN** future scheduled investigation logic calls an AI provider through the gateway
- **THEN** the provider SHALL receive only bounded sanitized prompts and metadata
- **AND** it SHALL NOT receive database handles, API dispatch handles, shell access, file access, or approval callbacks
