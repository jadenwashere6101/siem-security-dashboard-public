# Proposal: SOAR Worker Admin Run Control

## Problem

The SOAR worker can process queued actions through `process_batch()` and the
manual CLI runner (`scripts/soar_worker_run.py`), but there is no admin-protected
backend control for running one bounded batch from the UI/API. During early SOAR
operation, admins need a safe way to drain a small number of queued simulation
actions without opening a shell on the host.

This control must be intentionally narrow. It is not a daemon, scheduler, replay
system, or real adapter execution surface.

## Goal

Add an admin-only backend endpoint that runs exactly one SOAR worker batch and
returns a summary.

Suggested endpoint:

```text
POST /admin/soar/worker/run-once
```

The first version must default to simulation mode and must reject or ignore any
attempt to run real firewall/cloud adapters.

## In Scope

- Admin-only backend endpoint.
- One request triggers at most one bounded `process_batch()` call.
- Simulation executor only.
- Safe batch-size validation and hard maximum.
- Summary response with counts and per-item results.
- Audit/logging of who triggered the run if existing audit helper fits.
- Tests for auth, admin guard, batch-size behavior, response shape, simulation
  enforcement, and expected queue mutation from normal worker processing only.

## Out of Scope

- No scheduler/systemd.
- No daemon.
- No real firewall execution.
- No playbooks/incidents.
- No retry/replay individual item controls.
- No frontend button yet.
- No ingest/detection/correlation changes.
- No schema changes.
- No distributed worker behavior.

## Success Criteria

- Unauthenticated callers receive `401`.
- Non-admin callers receive `403`.
- Super-admin caller can trigger one simulation batch.
- Endpoint clamps or rejects excessive batch size.
- Endpoint returns a clear summary.
- Endpoint uses `SimulationExecutor`.
- Endpoint does not accept real execution mode.
- Queue mutation is limited to normal worker processing:
  - pending rows may become running then success/skipped/failed/requeued
  - unrelated terminal rows do not change
  - no schema or queue metadata outside worker behavior changes

