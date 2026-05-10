# Proposal: SOAR Playbook Metrics Frontend

## Problem

The backend `GET /metrics/playbooks` endpoint exists and returns aggregated playbook
execution counts: total executions, counts broken down by status, counts broken down by
playbook ID, recent success and failure counts within a 24-hour window, and
approval-gated execution counts. There is no frontend panel or section that surfaces
this data. Verifying playbook execution health currently requires direct API inspection
or reading the database.

## Goal

Add a read-only frontend metrics panel that calls `GET /metrics/playbooks` and displays
aggregated playbook execution state: total executions, status breakdown, recent activity
window, approval-gated counts, and a per-playbook summary. The panel must make clear
that all executions are simulation-only and that no real integrations or remediation
actions have occurred.

## Scope

- Add a frontend service helper for `GET /metrics/playbooks`.
- Add a read-only `PlaybookMetricsPanel` component showing:
  - Total execution count.
  - Status breakdown across all six known statuses.
  - Recent success and failure counts with the 24-hour window labeled.
  - Approval-gated counts: executions currently awaiting approval and executions
    that have ever had a linked approval request.
  - Per-playbook breakdown: playbook ID, total, and status counts.
- Add loading, error, and empty states.
- Add focused frontend tests covering rendering, state transitions, defensive field
  access, and the labeling that all data reflects simulation-only executions.

## Out of Scope

- No implementation code in this proposal.
- No backend changes.
- No schema changes.
- No executor behavior changes.
- No mutation controls of any kind.
- No run, retry, cancel, abandon, or approve controls.
- No real integrations.
- No ingest, detection, or correlation changes.
- No daemon or systemd worker changes.

## Success Criteria

- Authenticated analyst and super-admin users can view playbook execution metrics in
  the frontend without leaving the dashboard.
- The panel labels all metrics as simulation-only playbook execution data.
- Total executions, status breakdown, recent window counts, approval-gated counts, and
  per-playbook breakdown are all visible.
- The recent window note ("last 24 hours") is displayed alongside the counts.
- The panel renders a useful empty state when `total_executions` is zero and all
  status counts are zero.
- The panel renders a user-friendly error state if the API call fails.
- No mutation controls, run buttons, retry buttons, or execute controls appear anywhere
  in the panel.
- Existing Playbooks, SOAR Queue, Approvals, Incidents, and Integration Status panel
  tests remain unaffected.
- No backend, schema, executor, or queue files are modified.
