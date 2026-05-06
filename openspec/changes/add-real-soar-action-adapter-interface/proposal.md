# Proposal: Real SOAR Action Adapter Interface

## Problem

The SOAR queue, post-commit enqueue path, worker, simulation executor, detection
decoupling, and worker audit logging are now in place. The next architectural
risk is adding real firewall, cloud, or SaaS integrations directly into the
worker or `SimulationExecutor`.

That would make dangerous side effects hard to review, hard to test, and hard to
disable. Before any real blocking or notification integration is added, the
project needs a clean adapter interface layer that defines how real actions plug
into the existing executor/worker contract.

## Goal

Design the first real adapter architecture for SOAR response actions.

This change defines:

- the adapter interface contract
- the adapter result format
- how adapters connect to the existing `SimulationExecutor` and worker seam
- where adapter code lives
- how adapters are selected and configured
- retryable vs skipped vs terminal failure classification
- timeout and logging expectations
- safety controls for dangerous actions
- a testing strategy that avoids real network or firewall calls

## Current SOAR foundation

Already available:

- `response_actions_queue`
- queue store helpers
- `engines/soar_action_worker.py`
- `engines/soar_executor.py` with `SimulationExecutor`
- `engines/soar_errors.py` with `RetryableActionError` and `SkippedAction`
- post-commit enqueue from ingest routes
- detection decoupled from synchronous response execution
- worker-side `response_actions_log` audit logging

The worker already accepts an injected executor callable. This is the seam the
adapter interface should build on.

## In scope

- Define a shared adapter protocol for future real integrations.
- Define a registry/factory pattern that chooses simulation vs real adapter
  execution.
- Define result and exception contracts compatible with the current worker.
- Define validation, timeout, logging, and safety expectations.
- Explicitly discuss future adapters:
  - Linux firewall (`iptables`/`ufw`)
  - Windows firewall
  - Azure Network Security Groups
  - AWS Security Groups
  - Slack notifications
  - Email notifications
- Define tests for interface behavior using fake adapters and simulation only.

## Out of scope

- No real firewall implementation.
- No cloud credentials.
- No network calls.
- No frontend changes.
- No playbooks or incidents.
- No distributed workers.
- No production implementation in this spec-only change.
- No test edits in this spec-only change.
- No queue schema changes.
- No worker audit logging changes.

## Success criteria

- Future real integrations have a clear place to live and a stable interface to
  implement.
- The worker can keep its existing public executor contract.
- Simulation remains the default and test-safe path.
- Real adapters are opt-in through explicit configuration.
- Dangerous actions require explicit safety controls before execution.
- Failure modes map cleanly to existing worker behavior:
  - `SkippedAction` -> terminal skipped
  - `RetryableActionError` -> retry while attempts remain
  - non-retryable adapter failure -> terminal failed

