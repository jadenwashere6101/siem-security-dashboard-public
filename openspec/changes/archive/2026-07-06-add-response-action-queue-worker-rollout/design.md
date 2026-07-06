## Context

The SOAR platform has two separate worker paths:

- `scripts/soar_playbook_worker_daemon.py` processes `playbook_executions`.
- `scripts/soar_worker_run.py` processes `response_actions_queue`.

The deployed VM currently runs `soar-playbook-worker.service`, but no systemd
service, timer, or cron entry processes `response_actions_queue`. The live queue
therefore accumulated 57 pending rows, mostly `block_ip`, while the playbook
worker logs show `processed=0` because it is looking at a different queue.

`block_ip` is high risk and already requires approval in
`engines/soar_action_worker.py`. In default simulation mode, running the
response-action worker should not enforce firewall changes; it should move
`block_ip` rows into `awaiting_approval` and process lower-risk simulated actions
to terminal states.

## Goals / Non-Goals

**Goals:**

- Provide a safe one-time backlog drain plan using the existing response-action
  runner in simulation mode.
- Add durable deployment automation for the response-action queue worker through
  a bounded systemd service/timer or equivalent operator-managed unit.
- Make the response-action worker visibly separate from the playbook worker.
- Preserve approval gating for `block_ip`.
- Preserve firewall dry-run/tracking-only safety boundaries.
- Add verification and rollback steps for the VM rollout.

**Non-Goals:**

- Do not merge the response-action worker and playbook worker in this change.
- Do not enable real firewall enforcement.
- Do not bypass approval for `block_ip`.
- Do not change detection or enqueue rules.
- Do not change frontend components.
- Do not create migrations.
- Do not delete pending queue rows as a substitute for processing them.

## Decisions

### Decision 1: Reuse `scripts/soar_worker_run.py`

Use the existing runner as the execution unit for both one-time drain and
recurring automation.

Rationale:

- It already calls `engines.soar_action_worker.process_batch`.
- It honors `SOAR_EXECUTION_MODE`, batch size, and simulation executor behavior.
- It is covered by existing runner/worker tests.

Alternative considered: build a new daemon. Rejected for this fix because the
missing piece is deployment orchestration, not a new execution engine.

### Decision 2: Prefer systemd timer over always-on daemon for response actions

Deploy an operator-managed one-shot service plus timer, such as:

- `soar-response-action-worker.service`
- `soar-response-action-worker.timer`

The service runs one bounded batch and exits. The timer invokes it periodically.

Rationale:

- Bounded batches reduce blast radius.
- Timer cadence is easy to stop, inspect, and rollback.
- The existing runner is a one-shot command, not a long-running daemon.

Alternative considered: run an infinite loop daemon. Rejected until there is a
separate design for leases/heartbeats equivalent to the playbook worker daemon.

### Decision 3: Simulation mode is mandatory by default

The service/timer must set:

```text
SOAR_EXECUTION_MODE=simulation
SOAR_RUNNER_BATCH_SIZE=<bounded value>
```

Real mode must not be enabled by this change. If real mode support is needed
later, it requires a separate approved spec.

### Decision 4: Backlog drain is explicit and observable

Before any drain:

1. Record `response_actions_queue` counts by status and action.
2. Record oldest/newest pending timestamps.
3. Confirm service/timer is disabled or not yet installed.
4. Run one bounded batch in simulation mode.
5. Recheck counts and inspect transitions.

Only after a sample batch behaves as expected should additional batches or the
timer be enabled.

Expected transitions:

- `monitor` and `flag_high_priority` may complete with `success`.
- `block_ip` should move to `awaiting_approval` unless skipped by protected
  target validation.
- Failures should stay bounded by retry/max retry behavior and visible status.

### Decision 5: Rollback disables scheduling, not data

Rollback should stop/disable the timer and service. It should not delete queue
rows, approval requests, response logs, or canonical outcome events.

## Risks / Trade-offs

- [Risk] Timer processes too many items too quickly. -> Mitigation: bounded
  batch size, timer cadence, sample batch before enablement.
- [Risk] Operators confuse playbook worker health with response-action queue
  health. -> Mitigation: separate service names and runbook checks.
- [Risk] `block_ip` appears to execute. -> Mitigation: simulation mode,
  approval gate, firewall boundary documentation, and verification that rows
  move to `awaiting_approval` rather than real enforcement.
- [Risk] Existing backlog is stale demo data. -> Mitigation: do not delete by
  default; process through normal worker states or explicitly document any later
  operator cleanup as separate.
- [Risk] `DATABASE_URL` construction differs between local and VM envs. ->
  Mitigation: deployment/runbook must source the VM `.env` and verify a dry-run
  status command before enabling the timer.

## Migration Plan

1. Add deployment artifacts or runbook commands for a response-action worker
   one-shot systemd service and timer.
2. Add a preflight command that prints queue counts without mutation.
3. Run a one-time bounded simulation batch against the VM and record before/after
   counts.
4. Enable timer only after the sample batch behaves correctly.
5. Verify dashboard queue counts decline or move into expected approval states.
6. Roll back by stopping/disabling the timer and service.

No database migration is required.

## Open Questions

- What timer cadence should production use: every 1 minute, 5 minutes, or a
  slower demo-safe cadence?
- Should backlog drain stop after `block_ip` rows are awaiting approval, or
  should operators approve/deny them as part of a separate cleanup?
- Should the dashboard add an explicit indicator that response-action worker
  scheduling is enabled, or is existing queue/metrics visibility sufficient?
