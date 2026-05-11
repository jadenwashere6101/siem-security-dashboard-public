# Proposal: SOAR Playbook Read APIs

## Problem

The SOAR playbook foundation now has database tables, store helpers, a registry scaffold,
and pure trigger matching, but operators still cannot inspect playbook definitions or
playbook execution records through the backend API. The only visibility is direct database
access or tests.

This makes it hard to validate configured playbook definitions, inspect existing execution
records, or build future operator UI safely before any executor or ingest wiring is added.

## Goal

Add read-only backend API visibility for SOAR playbook data:

- `GET /playbooks` to list playbook definitions.
- `GET /playbooks/<id>` to return one playbook definition.
- `GET /playbook-executions` to list execution records with filters.
- `GET /playbook-executions/<id>` to return one execution record.

The APIs should use existing auth/admin patterns and existing `core/playbook_store.py`
helpers where possible. They must not create, update, delete, enqueue, execute, or trigger
any playbook work.

## Scope

- New read-only route module, likely `routes/playbook_routes.py`.
- Route registration in `siem_backend.py` only if that matches the existing app pattern.
- JSON serializers for playbook definitions and execution records.
- List filtering and safe limit handling for execution records.
- Tests for authentication, authorization, response shape, filtering, not-found behavior,
  and no mutation.

## Out of Scope

- No implementation code as part of this proposal.
- No schema changes.
- No frontend changes.
- No playbook create/update/delete APIs.
- No playbook executor.
- No playbook step execution.
- No ingest route wiring.
- No detection or correlation changes.
- No SOAR queue changes.
- No Slack, email, firewall, or other integration work.
- No real execution mode.
- No automatic creation of `playbook_executions` from alerts.

## Success Criteria

- Unauthenticated callers cannot access playbook read endpoints.
- Unauthorized authenticated users cannot access playbook read endpoints.
- Authorized operators can list and retrieve playbook definitions.
- Authorized operators can list and retrieve playbook execution records.
- Execution list filters work for `playbook_id` and `status`.
- Invalid filters or malformed IDs return safe 4xx responses.
- Missing definitions or executions return `404`.
- Calling any endpoint does not mutate `playbook_definitions`, `playbook_executions`,
  SOAR queue rows, alerts, incidents, approvals, or response action logs.
- Existing SOAR queue, incident, approval, protected-target, dry-run adapter, ingest,
  detection, and correlation behavior remains unchanged.
