## Why

SOAR execution has reached the point where the current manual single-run executor is useful for controlled validation, but it is not sufficient for reliable day-to-day orchestration. The system already has playbook executions, execution leases, stale recovery, dead letters, retry controls, SOAR Operations UI, metrics dashboarding, and a simulation-safe execution model. The next phase should turn those foundations into a continuously running worker model without weakening safety boundaries.

The goal is to evolve from "operator starts one executor run" to "a managed worker process continuously claims, executes, recovers, and reports work" while preserving the existing ingest, detection, correlation, approval, dead-letter, and simulation contracts.

## What Changes

- Define a dedicated SOAR worker daemon process with safe polling cadence, shutdown handling, backpressure controls, and starvation prevention.
- Define single-worker and multi-worker behavior around lease acquisition, lease renewal, stale recovery, retry coordination, and duplicate execution prevention.
- Harden execution idempotency boundaries so a playbook execution cannot be processed twice when workers overlap, crash, or reconnect.
- Add an operational visibility model for worker health, worker heartbeats, queue depth, stale execution counts, recovery counts, and failure-rate metrics.
- Define failure handling for worker crashes, mid-step lease expiry, database disconnects, poison executions, retry exhaustion, and dead-letter escalation.
- Define deployment expectations for a future systemd service, environment requirements, logging, restart policy, graceful shutdown, and safe rollout.
- Define load and validation planning for concurrent workers, queue pressure, stale recovery, failure injection, and verification.

## Capabilities

### New Capabilities

- `soar-worker-orchestration`: continuous daemonized SOAR worker execution, safe multi-worker leasing, recovery loops, operational visibility, deployment planning, and load-validation requirements.

### Modified Capabilities

- Existing playbook execution, lease recovery, dead-letter, retry, and SOAR metrics capabilities will be extended only through small additive changes needed for continuous orchestration. No schema rewrites or runtime integrations are proposed.

## Impact

- Future implementation will likely touch the manual worker/executor entrypoint, playbook execution store, dead-letter store, metrics routes, operational dashboards, and deployment documentation.
- Any persistence changes must be additive and separately reviewed; no schema rewrite is allowed.
- Real Slack, Teams, firewall, or other external adapter execution must remain disabled by default.
- Ingest, detection, and correlation contracts must remain unchanged.
- This change is design-only until approved for implementation slices.
