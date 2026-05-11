# Proposal: SOAR Playbook Execution Metrics

## Problem
SOAR playbook definitions, execution records, simulation-only step execution, approval gates, execution controls, simulation integration adapters, and frontend execution visibility now exist. Operators can inspect individual playbook executions, but there is not yet a read-only backend metrics endpoint that summarizes execution health across playbooks.

Without a backend metrics API, operational questions such as "how many executions are pending", "which playbooks are failing", or "how many executions are waiting on approval" require direct database inspection or manual aggregation.

## Goal
Add read-only backend metrics for SOAR playbook executions.

## Scope
- Add a read-only metrics endpoint, likely `GET /metrics/playbooks`.
- Report total playbook execution count.
- Report execution counts by status: `pending`, `running`, `awaiting_approval`, `success`, `failed`, and `abandoned`.
- Report execution counts grouped by `playbook_id`.
- Report recent success and failure counts over a small, documented time window.
- Report approval-gated execution counts when safely available from existing execution or approval data.
- Use existing auth and role patterns for analyst and super-admin visibility.
- Add focused backend tests for the metrics behavior.

## Out of scope
- No implementation code in this change.
- No frontend changes.
- No schema changes unless implementation proves an existing-index-only query is unsafe or insufficient.
- No executor behavior changes.
- No playbook scheduling behavior changes.
- No playbook retry, abandon, or resume behavior changes.
- No real Slack, email, webhook, firewall, PagerDuty, or outbound integration execution.
- No daemon, systemd, Celery, APScheduler, or background worker.
- No SOAR queue changes.
- No ingest, detection, or correlation changes.

## Success criteria
- Authenticated allowed users can call a read-only playbook metrics endpoint.
- The endpoint returns stable counts by status, total executions, and executions grouped by `playbook_id`.
- The endpoint returns recent success and failure counts using a documented time window.
- Approval-gated counts are included only if they can be computed safely from existing read-only data.
- Tests prove the endpoint does not mutate playbooks, executions, approvals, queue rows, alerts, or incidents.
- Existing playbook execution, approval, SOAR queue, ingest, detection, and correlation behavior remains unchanged.
