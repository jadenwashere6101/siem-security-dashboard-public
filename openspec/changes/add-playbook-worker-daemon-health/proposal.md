## Why

The SOAR playbook worker dashboard currently reports `daemon_health.status = "unknown"` even when the daemon is running normally, because no process-level heartbeat is persisted outside active playbook execution leases. Operators and analysts need truthful worker health states that distinguish never-seen, healthy, late, and offline daemon conditions without changing playbook execution behavior.

## What Changes

- Add a persisted daemon heartbeat for the playbook worker that updates on a bounded cadence even when the queue is idle.
- Derive deterministic worker health states from that persisted heartbeat: `unknown`, `healthy`, `degraded`, and `offline`.
- Extend the existing `/metrics/playbook-worker` contract to return the current health status, last heartbeat timestamp, process start time, uptime, safe build/version metadata when available, and concise reason text.
- Update the existing SOAR worker health UI to render an accessible status badge, last heartbeat timestamp, start time/uptime, build/version when available, and clear explanatory copy for normal, stale, offline, loading, error, and never-seen states.
- Preserve existing execution lease heartbeats, stale-recovery semantics, retries, approvals, protected-target handling, and playbook execution logic unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `soar-worker-orchestration`: Replace the current always-unknown daemon health presentation with a persisted process heartbeat and deterministic worker health states in the existing worker metrics/UI surfaces.

## Impact

- Backend worker runtime: `engines/soar_playbook_worker.py` and `scripts/soar_playbook_worker_daemon.py` will need a lightweight heartbeat emission path that is independent of active executions.
- Database/schema: an additive heartbeat persistence table and migration are expected so health can survive restarts, distinguish `unknown` versus `offline`, and expose start/build metadata without affecting playbook execution rows.
- Backend API: `GET /metrics/playbook-worker` will shift from DB-derived queue-only health to a mixed queue-plus-daemon-health contract while preserving existing RBAC and read-only behavior.
- Frontend UI: the Worker Operations section in the SOAR metrics surface will present clear non-color-only health states, last heartbeat time, and reason text in both desktop and narrow layouts.
- Tests/docs: worker, API, UI, migration, and runbook coverage will expand to prove idle-worker health, stale/offline transitions, restart recovery, DB failure handling, and unchanged execution lease behavior.
