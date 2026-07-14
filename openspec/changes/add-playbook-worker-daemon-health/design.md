## Context

The current playbook worker daemon exists and can process work continuously, but the worker metrics route intentionally hard-codes `daemon_health.status = "unknown"` because no process-level heartbeat is persisted. Existing `lease_heartbeat_at` values belong to individual running executions and cannot prove that an idle daemon is alive. The UI therefore reports an accurate but operationally weak unknown state even when the worker process is healthy.

This change is intentionally narrow. It must improve daemon health reporting in the existing SOAR metrics/operations surfaces without redesigning the worker, changing execution leasing, altering retry/approval behavior, or introducing worker-management controls.

## Goals / Non-Goals

**Goals:**
- Persist a lightweight playbook-worker daemon heartbeat that exists independently of active playbook executions.
- Define exact cadence and thresholds for `unknown`, `healthy`, `degraded`, and `offline`.
- Expose daemon health through the existing `/metrics/playbook-worker` contract with `status`, `last_heartbeat_at`, and concise explanatory copy.
- Update the existing UI surfaces to display accessible health state, last heartbeat, and never-seen/loading/error handling.
- Preserve current execution lease heartbeats and prove they are unchanged.

**Non-Goals:**
- No worker redesign, multi-worker orchestration, or historical heartbeat analytics.
- No charts, notifications, alerting, or worker-management controls.
- No replacement of execution lease heartbeats with daemon health data.
- No changes to playbook execution semantics, approvals, dead-letter policy, or protected-target enforcement.
- No VM access, deploy, or production mutation in this spec-authoring step.

## Decisions

### Heartbeat persistence location

Add a new additive PostgreSQL table, `soar_worker_heartbeats`, keyed by logical worker name (initially only `playbook_worker`), with one current row per worker. The row stores:
- `worker_name`
- `worker_instance_id`
- `build_version`
- `started_at`
- `last_heartbeat_at`
- `updated_at`

Rationale: the backend already derives worker metrics from PostgreSQL, and a single current row cleanly distinguishes `unknown` (no row ever written) from `offline` (row exists but heartbeat is too old). Reusing `playbook_executions` would fail for idle workers, and log-derived or systemd-only health would not fit the existing authenticated API contract. Keeping `worker_name` and `worker_instance_id` future-proofs the table shape without introducing multi-worker orchestration behavior in this change.

Alternative considered: append-only heartbeat history. Rejected because the request explicitly excludes historical analytics and the extra write/storage cost adds no value for the current UI.

### Migration and retention

This change requires a schema migration because no existing durable table can hold daemon-level heartbeat data without conflating it with execution rows. The table retains the latest row indefinitely and overwrites it in place per worker name; no cleanup job is required.

Rationale: retaining the latest row indefinitely preserves the distinction between "never seen" and "seen before but currently offline." Deleting rows would erase that operational meaning.

### Heartbeat cadence and thresholds

Use a bounded daemon heartbeat cadence of 15 seconds with exact API thresholds:
- `unknown`: no heartbeat row exists
- `healthy`: last heartbeat age is 0-45 seconds inclusive
- `degraded`: last heartbeat age is greater than 45 seconds and up to 120 seconds inclusive
- `offline`: last heartbeat age is greater than 120 seconds

Rationale: the current daemon can idle for roughly 30 seconds, so a 15-second cadence requires explicit heartbeat scheduling independent of work but keeps `healthy` tolerant of one or two delayed writes. A 120-second offline threshold avoids declaring the worker offline during brief restart or DB recovery windows while still surfacing a real liveness problem quickly.

### Worker emission behavior

The daemon writes an initial heartbeat on startup and refreshes it at least every 15 seconds while running, even when no executions are claimed. Implementation should cap idle sleeping to the next heartbeat deadline rather than tying heartbeat writes only to queue activity.

Rationale: this keeps idle workers healthy without reducing batch-processing behavior or repurposing execution lease renewal.

Alternative considered: heartbeat only at loop boundaries. Rejected because the current idle backoff can exceed a useful liveness interval and would reintroduce false degraded/offline states for healthy idle workers.

### API contract

Keep the existing `daemon_health` object and extend it rather than creating a new endpoint. The contract should include:
- `status`: `unknown | healthy | degraded | offline`
- `worker_heartbeat_available`: `false` only when no heartbeat has ever been recorded
- `last_heartbeat_at`: ISO-8601 timestamp or `null`
- `started_at`: ISO-8601 timestamp or `null`
- `uptime_seconds`: non-negative integer or `null`
- `build_version`: deterministic build identifier or `null`
- `message`: concise status reason suitable for direct UI display

`source` may continue to exist, but daemon health semantics are defined by the heartbeat contract above rather than queue-only snapshots.

Rationale: this is the smallest compatible change for the existing frontend service and tests.

### Restart and failure semantics

On worker restart, the daemon updates the same logical worker row with a new `worker_instance_id`, a fresh `started_at`, and an immediate heartbeat, allowing the API to recover from `offline` or `degraded` to `healthy` on the first successful write. If heartbeat persistence fails because the database is unavailable, the worker logs the failure and follows existing bounded retry/backoff behavior; the backend health state naturally ages from `healthy` to `degraded` or `offline` until writes resume.

Rationale: no synthetic "healthy" state should be manufactured during DB failure, and heartbeat errors must not mutate playbook processing semantics to compensate.

### Build/version metadata

The worker should capture a deterministic build identifier at startup and persist it with the heartbeat row when it can be obtained safely. The preferred source is the current repository short git SHA resolved locally with a bounded, non-interactive command and an `unknown`/`null` fallback when unavailable.

Rationale: the deployed worker process is the most truthful source of its own build identity, and storing it with the heartbeat ties the health record to the build actually running. This stays within daemon-health observability scope and avoids introducing a broader deployment metadata service.

### UI behavior

Use the existing Worker Operations surface. Replace the current generic unknown presentation with:
- a clear text status badge
- last heartbeat timestamp
- process start time and uptime
- build/version when available
- a concise explanation from the API
- explicit never-seen copy for `unknown`
- accessible loading and error copy
- layout-safe rendering for desktop and narrow screens without color-only meaning

Rationale: the user asked for better states in the existing surfaces, not a new dashboard or analytics view.

## Risks / Trade-offs

- [Heartbeat writes increase DB churn] -> Mitigation: one upsert every 15 seconds for a single worker row is bounded and far smaller than execution-step writes.
- [Idle worker still appears stale if heartbeat scheduling depends on long sleep paths] -> Mitigation: require heartbeat emission independent of queue activity and cap sleep by next heartbeat deadline.
- [Restart windows briefly appear degraded or offline] -> Mitigation: startup writes heartbeat immediately and offline threshold is wider than one normal restart cycle.
- [DB outage makes health appear offline even if the process is still alive] -> Mitigation: treat persisted DB heartbeat as the source of truth for the API, surface concise reason text, and preserve existing worker retry/backoff logs for deeper diagnosis.
- [Implementation accidentally mixes daemon and execution lease heartbeats] -> Mitigation: keep separate storage/helpers/tests and add explicit non-regression coverage around `lease_heartbeat_at`.

## Migration Plan

1. Add the additive `soar_worker_heartbeats` table and migration.
2. Add backend store/helper logic to upsert and read the current playbook-worker heartbeat row.
3. Update the daemon to emit startup and periodic idle-safe heartbeats.
4. Update `/metrics/playbook-worker` to derive deterministic daemon states and expose the new fields.
5. Update the existing SOAR metrics UI and focused tests.
6. Run migration/schema validation, focused backend/frontend tests, production build, `openspec validate --strict`, and `git diff --check`.
7. Prepare a VM handoff that restarts `siem-backend.service` and `soar-playbook-worker.service` after the approved migration is applied.

## Open Questions

None. This spec resolves the persistence model, migration need, cadence, thresholds, restart semantics, failure semantics, retention model, start/uptime behavior, build/version behavior, and UI contract.
