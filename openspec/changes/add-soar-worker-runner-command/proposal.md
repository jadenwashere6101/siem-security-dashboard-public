# Proposal: SOAR Worker Runner Command

## Problem

The SOAR queue, worker, executor, and adapter layers are fully implemented and
tested in isolation. Actions are enqueued after detection commits. Nothing
processes them.

There is no way to run queued actions outside of a test harness. To validate
the full stack — enqueue → claim → execute → audit — an operator must write a
custom script or trigger a test that manually calls `process_batch`. This
creates friction in development and makes end-to-end flow validation difficult.

A manual runner command is the missing bridge between the queue and the worker.

## Goal

Add a single CLI-invocable command that processes a bounded batch of queued
SOAR actions on demand. It must be safe to run by default, produce clear output,
and be testable without any external side effects.

## What This Change Introduces

- A runnable CLI entry point: `python -m scripts.soar_worker_run` (or
  equivalent — exact placement determined in design).
- Configurable batch size with a safe default and enforced maximum.
- `SimulationExecutor` as the default executor — no real actions taken unless
  explicitly configured.
- Optional opt-in to `AdapterBackedExecutor` via environment configuration.
- Printed/logged summary: processed / success / failed / skipped / requeued
  counts.
- Clean exit codes: 0 on successful run (even if some actions failed), non-zero
  on configuration or startup errors.

## What This Change Does Not Introduce

- No daemon or long-running process.
- No scheduler, cron wiring, or systemd unit.
- No real firewall execution (guarded by config, not code changes).
- No new queue schema changes.
- No new database tables.
- No changes to ingest, detection, or correlation logic.
- No frontend or API endpoint.
- No playbook/incident concepts.
- No cloud action adapters.

## Safety Constraints

- Default execution mode is simulation. The operator must explicitly set
  `SOAR_EXECUTION_MODE=real` to route through `AdapterBackedExecutor`.
- Batch size defaults to 10, maximum 50. Both values are enforced in code, not
  just documentation.
- The runner must refuse to execute if called from inside an ingest or request
  context (guard at startup).
- The runner must print a clear header indicating execution mode before
  processing begins.
- All result counts must be printed at exit regardless of success or failure.

## Fit in the SOAR Roadmap

This is the "run it manually" phase, immediately before the systemd/cron phase.
It replaces ad-hoc test-based invocation with a stable, production-worthy entry
point that can later be wrapped by a scheduler without code changes.

The runner is deliberately thin. It calls existing code. Its only unique
contribution is the CLI surface, safety configuration, and summary output.
