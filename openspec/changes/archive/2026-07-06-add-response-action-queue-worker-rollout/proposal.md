## Why

The deployed dashboard currently shows a real `response_actions_queue` backlog:
57 pending rows, mostly `block_ip`, with some pending since 2026-06-23. The VM
runs the playbook worker daemon, but there is no service/timer/cron draining the
separate response-action queue runner, so queued alert responses accumulate.

## What Changes

- Add a controlled response-action queue worker rollout that covers both:
  - one-time simulation-safe backlog processing, and
  - durable automated processing through an operator-managed service or timer.
- Preserve the existing `block_ip` approval gate: queued block actions must move
  to approval flow, not real firewall enforcement.
- Keep default execution mode simulation-safe and forbid autonomous real firewall
  enforcement.
- Add deployment/runbook documentation for queue depth checks, dry-run status,
  one-time drain, service/timer enablement, rollback, and stop conditions.
- Add verification for queue status transitions and operational visibility.
- Do not change alert detection, queue enqueue rules, approval policy, playbook
  worker behavior, canonical outcome semantics, or frontend components unless an
  implementation task explicitly identifies a narrow compatibility bug.

## Capabilities

### New Capabilities

- `response-action-queue-worker-rollout`: Controlled operation and deployment of
  the response-action queue runner that processes `response_actions_queue`.

### Modified Capabilities

- None. The existing `soar-worker-orchestration` capability covers playbook
  execution workers and is intentionally left separate.

## Impact

- Affected code may include `scripts/soar_worker_run.py`, deployment artifacts
  under `deploy/systemd/` or docs, and focused tests for the response-action
  worker rollout path.
- Affected runtime system: deployed VM systemd/timer configuration for
  response-action queue processing.
- Affected data: existing pending `response_actions_queue` rows may transition
  to `awaiting_approval`, `success`, `skipped`, or `failed` during the approved
  one-time drain.
- No database migration is expected.
