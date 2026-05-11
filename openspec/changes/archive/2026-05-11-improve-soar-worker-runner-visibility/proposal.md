# Proposal: Improve SOAR Worker Runner Visibility

## Problem

`scripts/soar_worker_run.py` was implemented correctly, but its CLI surface is
incomplete and its output is not machine-readable. Specifically:

- `argparse` is imported and `--batch-size` is defined, but `parse_known_args()`
  discards the result. CLI args have no effect — everything is still env-var only.
- `--mode`, `--json`, and `--dry-run-info` flags do not exist.
- There is no way to inspect queue state without triggering processing.
- Summary output is human-readable plain text only, which cannot be consumed
  by tests, CI, or future tooling without string parsing.

This blocks two practical workflows: running the runner in a demo or on a VM
where passing args is more natural than setting env vars, and auditing queue
state before deciding whether to run the worker.

## Goal

Make the runner more usable by:

1. Wiring CLI args properly so they override env vars.
2. Adding `--mode simulation|real` and `--json` flags alongside the already-
   defined but unconnected `--batch-size`.
3. Adding `--dry-run-info` (name chosen to avoid collision with the adapter's
   dry-run concept): a read-only mode that prints queue status counts without
   processing any actions.
4. Keeping env vars as the fallback defaults so existing tooling and tests
   continue to work without modification.

## What This Change Introduces

- Properly wired `--batch-size` CLI arg (overrides `SOAR_RUNNER_BATCH_SIZE`).
- New `--mode simulation|real` CLI arg (overrides `SOAR_EXECUTION_MODE`).
- New `--json` flag: all output (header, per-action results, summary) is
  serialized as a single JSON object to stdout.
- New `--dry-run-info` flag: prints pending/running/failed/skipped/success
  counts from the queue and exits 0. No rows are claimed, no actions are
  processed, no state is mutated.
- A small read-only queue count helper in `core/response_action_queue_store.py`
  to support `--dry-run-info`. One new function, no schema changes.
- Tests for arg wiring, env fallback precedence, JSON output shape, and
  `--dry-run-info` read-only behavior.

## What This Change Does Not Introduce

- No daemon, scheduler, or systemd wiring.
- No real firewall execution.
- No schema changes.
- No new queue statuses.
- No changes to ingest, detection, or correlation logic.
- No frontend, API endpoint, or playbook concepts.
- No changes to `engines/soar_action_worker.py` or any existing queue
  transition logic.

## Why These Are Safe to Combine

All four additions (arg wiring, `--mode`, `--json`, `--dry-run-info`) touch
only `scripts/soar_worker_run.py` and one new read-only function in
`core/response_action_queue_store.py`. They share a single change surface,
have no interaction risks with each other, and require the same test setup.
Splitting them across multiple PRs would add overhead with no isolation benefit.
The visibility helper is trivially read-only. The JSON flag changes output
format, not execution behavior. The arg wiring is mechanical. These belong
together.
