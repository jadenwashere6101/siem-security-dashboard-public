# Proposal: SOAR Integration Adapter Health APIs

## Problem
SOAR simulation integration adapters exist and can be used by the playbook executor, but operators do not yet have a backend API to inspect which adapters are available, which actions they support, or whether the system is safely running in simulation mode. Without a read-only status endpoint, adapter visibility requires code or test inspection.

## Goal
Add read-only backend health/status visibility for SOAR integration adapters in simulation mode.

## Scope
- Add a read-only adapter status endpoint, such as `GET /integrations/status`.
- Return adapter names, supported actions, mode, simulated status, and real-mode disabled status.
- Use existing auth and role patterns for analyst or super-admin read access.
- Add backend tests proving the endpoint requires no secrets and makes no network calls.
- Keep adapter behavior, playbook executor behavior, and SOAR queue behavior unchanged.

## Out of scope
- No implementation code in this change.
- No real `test_connection` network calls.
- No real Slack, email, webhook, or firewall calls.
- No secrets or credential requirements.
- No schema changes.
- No frontend changes.
- No executor behavior changes.
- No SOAR queue changes.
- No ingest, detection, or correlation changes.
- No daemon or systemd worker.

## Success criteria
- Authenticated allowed users can call a read-only integration status endpoint.
- The response clearly reports simulation mode and that real mode is disabled or not implemented.
- The response lists each simulation adapter and its supported actions.
- Tests prove the endpoint does not require secrets and does not make network calls.
- Existing adapter, executor, playbook, SOAR queue, ingest, detection, and correlation tests continue to pass.
