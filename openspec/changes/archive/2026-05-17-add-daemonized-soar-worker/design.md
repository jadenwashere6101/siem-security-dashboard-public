## Context

The current SOAR system supports playbook executions, execution leases, stale recovery, dead letters, retry-request and retry-execute flows, SOAR Operations UI, SOAR Metrics dashboarding, a manual executor script, and simulation-safe adapter behavior. Execution is still operationally manual: an operator or test run starts the executor, the executor processes bounded work, and continuous orchestration is left outside the application.

This design moves the system toward a continuously running SOAR worker while preserving the existing safety model. The worker must not broaden remediation behavior, trigger real Slack/Teams/firewall actions by default, or change ingest/detection/correlation contracts. It should build on the existing lease and dead-letter foundations with small additive changes.

Primary stakeholders are analysts and super admins who need reliable SOAR queue processing, operators who need visibility into worker health, and developers who need deterministic tests for concurrency and failure recovery.

## Goals / Non-Goals

**Goals:**

- Define a daemonized worker process that continuously claims eligible playbook executions and processes them safely.
- Support single-worker and multi-worker deployments with lease contention safety and duplicate execution prevention.
- Add a stale lease recovery loop with bounded cadence and clear coordination with active workers.
- Add operational visibility for worker health, queue depth, stale executions, recoveries, and failures.
- Define failure handling for crashes, DB disconnects, poison executions, retry exhaustion, and dead-letter escalation.
- Define systemd deployment expectations without creating service files in this spec.
- Define validation coverage for concurrency, load, recovery, backpressure, and failure injection.

**Non-Goals:**

- No implementation in this design-only change.
- No real Slack, Teams, firewall, or external adapter execution enablement.
- No autonomous broad remediation rollout.
- No ingest, detection, or correlation changes.
- No schema rewrites. Any persistence changes must be additive and separately verified.
- No systemd unit creation until the worker implementation is validated.

## Decisions

### Dedicated Worker Process

The daemonized worker should be a dedicated process separate from the Flask web process. It should use the same store and executor primitives as the manual runner, but own its polling loop, shutdown handling, lease renewal, and recovery cadence.

Alternative considered: run continuous worker logic inside the Flask API process. This would simplify deployment count but couples request serving to long-running orchestration, complicates shutdown, makes worker health ambiguous, and increases blast radius.

### Polling With Bounded Cadence

The worker should poll for pending or retrying eligible executions at a configurable interval with jitter, batch size limits, and idle backoff. The polling loop must avoid tight DB loops when no work exists and avoid starving older eligible work when new executions arrive continuously.

Alternative considered: database notifications or a queue broker. Those may be useful later, but polling fits the current architecture and avoids adding infrastructure before concurrency semantics are fully validated.

### Lease-First Execution

Every execution attempt must begin with an atomic lease acquisition that transitions exactly one eligible execution into worker-owned processing. Workers must not execute an item unless the lease acquisition succeeds and returns ownership for that worker identity. Lease renewal and completion must check ownership.

Alternative considered: workers select pending rows then update them separately. That is simpler but creates race windows under multi-worker load.

### Idempotency Boundaries

Execution idempotency should be enforced at the execution-record level first. A worker must not re-run completed, failed, dismissed, dead-lettered, or lease-owned work. Step-level retries should continue to respect existing playbook executor semantics and approval gates. Retry-execute from dead letters should continue creating a new pending execution rather than mutating history.

Alternative considered: rely only on worker process uniqueness. That fails during crashes, restarts, or accidental multi-worker deployments.

### Integrated Recovery Loop

Stale recovery should run either inside one elected worker path or as a bounded operation each worker may attempt safely through transactional claims. Recovery must not mark an execution stale if an active owner has renewed its lease within the configured heartbeat window.

Alternative considered: keep recovery as a manual script only. Manual recovery is useful for break-glass operations but insufficient for a daemonized model.

### Operational Visibility

Worker visibility should include process identity, last heartbeat, current loop state, claimed counts, completion/failure counts, queue depth, stale execution counts, recovery counts, and dead-letter creation counts. Metrics should be read-only and RBAC-gated consistently with SOAR metrics and operations views.

Alternative considered: only emit logs. Logs are necessary but not enough for dashboard/API status, alerting, or automated validation.

### Simulation-Safe Deployment Default

The daemon should inherit the current simulation-safe execution model. Real adapters must remain disabled unless a separate explicit hardening and enablement change is approved. Worker deployment must not change adapter safety defaults.

Alternative considered: treat daemonization as the moment to enable real integrations. That mixes orchestration reliability with external side effects and makes rollback riskier.

## Worker Architecture

- A worker process starts with a stable `worker_id`, configuration validation, signal handlers, and a DB connectivity check.
- The main loop alternates among recovery, queue polling, lease renewal, execution, metrics heartbeat, and idle sleep.
- Polling uses batch limits and oldest-first ordering within eligible statuses to reduce starvation.
- Backpressure is handled by configurable max in-flight work per worker and batch size limits.
- Shutdown sets a draining flag, stops claiming new work, renews or releases active leases according to existing safe semantics, and exits after bounded cleanup.
- Multi-worker mode is a supported deployment state, not an accident. Correctness must depend on database transactions and lease ownership, not process uniqueness.

## Safe Concurrency

- Lease acquisition must be atomic and ownership-aware.
- Completion, failure, dead-letter creation, retry state transitions, and lease renewal must verify the worker still owns the lease.
- Retry-request and retry-execute flows must not race the worker into duplicate processing.
- Dead-letter coordination must preserve immutable failure history and only create new pending executions through the existing retry-execute semantics.
- Transaction boundaries should wrap claim, state transition, and audit/metric side effects where consistency matters.
- Queue visibility APIs must make leased, stale, retrying, failed, and pending states distinguishable.

## Failure Handling

- Worker crash: leases eventually become stale and are recovered by the recovery loop.
- Mid-step lease expiry: completion should fail ownership checks if the lease was recovered by another worker.
- DB disconnect: active work should fail closed, retry connection with bounded backoff, and avoid marking success without persisted completion.
- Poison execution: repeated execution failure should move through retry exhaustion and dead-letter escalation rather than looping forever.
- Retry exhaustion: retry counts and failure class should be visible in metrics and dead-letter detail.
- Dead-letter escalation: repeated retry failures should remain visible to analysts and super admins without auto-executing real remediation.

## Deployment Model

- A future systemd unit should run the worker as a dedicated service with the same environment source as the API where appropriate.
- Environment requirements should include database credentials, simulation mode flags, polling interval, batch size, lease duration, heartbeat interval, recovery interval, and log level.
- Logging should be structured enough to correlate `worker_id`, `execution_id`, lease owner, failure class, and retry path.
- Restart policy should prefer bounded automatic restart with clear logs rather than silent crash loops.
- Rollout should begin with one worker in simulation mode, then multi-worker simulation validation, then production-like load validation.

## Load / Validation Planning

- Unit tests should cover lease ownership, idempotency guards, retry coordination, and recovery classification.
- Integration tests should run multiple worker instances against the same database and prove single execution per item.
- Failure injection should simulate worker crash after lease, crash after step output before completion, DB disconnect, stale lease recovery, and dead-letter write failure.
- Queue pressure tests should validate batch caps, idle backoff, starvation prevention, and metrics accuracy.
- Dashboard/API tests should validate health and metrics read behavior without requiring a live daemon in normal frontend tests.

## Risks / Trade-offs

- Worker and API state transitions diverge -> Mitigation: centralize state changes in store functions and test them directly.
- Multiple workers duplicate execution -> Mitigation: atomic lease claims, ownership checks, and concurrency tests.
- Recovery reclaims active work too early -> Mitigation: conservative lease timeout defaults, heartbeat checks, and stale recovery simulations.
- Poison executions loop indefinitely -> Mitigation: retry caps, dead-letter escalation, and visible failure metrics.
- Operational dashboards imply real remediation is enabled -> Mitigation: persistent simulation-mode labeling and no real adapter enablement in this change.
- Systemd restart hides crash loops -> Mitigation: health metrics, structured logs, and bounded restart policy.

## Migration Plan

Implementation should be delivered in small slices. Start with store-level concurrency and worker-loop tests, then add the daemon process, then visibility APIs, then UI visibility, then deployment docs. Any additive schema requirement must be proposed and migrated separately before code depends on it. Rollback for early slices should be to stop the daemon and continue using the manual executor path.

## Open Questions

- Should worker heartbeat persistence use an existing table, an additive `soar_worker_heartbeats` table, or metrics derived from logs only?
- Should recovery run in every worker with transactional no-op safety, or should one worker be elected as recovery owner?
- What default lease duration, heartbeat cadence, polling interval, and stale recovery interval are safest for the VM deployment?
- Should response action queue execution be included in the same daemon after playbook execution is stable, or remain a separate later phase?
