## 1. Heartbeat Persistence and State Contract (Mac AI)

- [x] 1.1 Add an additive migration and schema updates for a durable `soar_worker_heartbeats` table keyed by logical worker name with current-instance, start-time, build-version, and heartbeat timestamps.
- [x] 1.2 Add backend store/helpers to upsert the `playbook_worker` heartbeat row, read the current row, and derive `unknown`, `healthy`, `degraded`, and `offline` plus start-time/uptime metadata using the spec thresholds.
- [x] 1.3 Add focused backend tests covering never-seen worker state, healthy heartbeat age, degraded transition, offline transition, and restart overwrite semantics.
- [x] 1.4 Run schema and migration validation for the new heartbeat table before any handoff.

## 2. Worker Heartbeat Emission (Mac AI)

- [x] 2.1 Add explicit daemon heartbeat cadence configuration/constants for a 15-second write interval and the matching health thresholds.
- [x] 2.2 Emit an initial heartbeat at daemon startup and refresh heartbeats on a bounded cadence independent of queue activity or active executions.
- [x] 2.3 Capture process start time and safe deterministic build/version metadata at startup and persist them with the daemon heartbeat when available.
- [x] 2.4 Ensure idle sleeping is capped by the next heartbeat deadline so an idle-but-running worker can remain healthy.
- [x] 2.5 Handle heartbeat write failures with logging and bounded retry/backoff behavior without changing lease renewal, approvals, retries, or playbook processing semantics.
- [x] 2.6 Add focused worker tests proving idle worker healthy, active worker healthy, worker restart recovery, DB write failure handling, start/build metadata capture, and no regression to execution lease heartbeat behavior.

## 3. Metrics API Integration (Mac AI)

- [x] 3.1 Update `GET /metrics/playbook-worker` to read persisted daemon heartbeat data and populate deterministic daemon health states instead of the current always-unknown sentinel.
- [x] 3.2 Extend the existing `daemon_health` contract with `last_heartbeat_at`, `started_at`, `uptime_seconds`, optional build/version metadata, and stable reason text while preserving RBAC and read-only behavior.
- [x] 3.3 Add API tests for authorized access, viewer denial, never-seen/healthy/degraded/offline transitions, and worker restart recovery.
- [x] 3.4 Confirm backend or DB failure paths do not fabricate healthy worker status and continue returning the existing route-level error behavior when metrics cannot be read.

## 4. UI Health States (Mac AI)

- [x] 4.1 Update the existing Worker Operations UI to render a clear text status badge, last heartbeat timestamp, process start time/uptime, build/version when available, and concise explanation from `daemon_health`.
- [x] 4.2 Add explicit UI behavior for loading, error, and never-seen worker states without relying on color alone.
- [x] 4.3 Verify desktop and narrow-layout rendering using the existing SOAR metrics or operations surfaces rather than adding new charts or controls.
- [x] 4.4 Add focused frontend tests for unknown, healthy, degraded, offline, loading, error, metadata fallback, and accessibility text states.
- [x] 4.5 Run a frontend production build after the UI changes.

## 5. Verification and VM Deployment Handoff (Mac AI -> VM AI on explicit authorization)

- [x] 5.1 Run focused backend worker, metrics API, migration, and non-regression tests covering idle health, active health, restart recovery, DB write failure, and unchanged playbook processing.
- [x] 5.2 Confirm no implementation path repurposes execution lease heartbeats or changes execution leasing, retries, approvals, dead-letter policy, or protected-target behavior.
- [x] 5.3 Run `openspec validate add-playbook-worker-daemon-health --strict`.
- [x] 5.4 Run `git diff --check`.
- [x] 5.5 Prepare a VM handoff describing migration order, backend and worker service restarts, health verification, rollback expectations, and explicit confirmation that deployment remains a separate VM AI step.
- [ ] 5.6 On explicit user authorization, have VM AI perform clean-tree sync, migration dry-run/apply, restart `siem-backend.service` and `soar-playbook-worker.service`, and capture sanitized before/after health evidence.
