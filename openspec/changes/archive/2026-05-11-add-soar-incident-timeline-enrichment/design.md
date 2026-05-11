# Design: SOAR Incident Timeline Enrichment

## Proposed architecture
Add read-only enriched timeline data to incident detail visibility. The implementation may either extend `GET /incidents/<id>` with a `timeline` field or add a separate endpoint such as:

```http
GET /incidents/<id>/timeline
```

A separate endpoint is preferable if the timeline query becomes large or if the existing incident detail response should remain stable. Extending detail is acceptable if the current frontend already treats incident detail as the authoritative incident view.

The timeline builder should aggregate existing records only. It must not execute playbooks, resume executions, update approvals, run queue workers, call integration adapters, or mutate incident state.

## Timeline sources
The timeline should include entries from these existing sources where available:

- Incident record: incident created, status, resolved timestamp if present.
- `incident_alerts`: alert linked to incident.
- `alerts`: alert details for linked alerts.
- `playbook_executions`: executions connected by `incident_id`, and optionally by linked alert IDs if the execution lacks `incident_id`.
- `playbook_executions.steps_log`: per-step events such as step started, simulated adapter output, approval requested, approval approved/resumed, denied, expired, failed, skipped, or aborted.
- `approval_requests`: approvals linked to `playbook_execution_id` and step index.
- `approval_request_events`: approval lifecycle events linked to those requests.
- `audit_log`: only events with a safe and explicit link to incident ID, alert ID, approval request ID, playbook execution ID, or route/action metadata that can be joined without fuzzy matching.

Do not infer audit links from free-text messages, usernames, IP addresses, or partial strings.

## Timeline entry shape
Use a stable normalized shape so frontend rendering and tests do not depend on raw table layouts:

```json
{
  "timestamp": "2026-05-10T18:25:00Z",
  "event_type": "playbook_step_completed",
  "source": "playbook_execution",
  "source_id": 123,
  "title": "Simulated Slack notification",
  "summary": "notify_slack completed in simulation mode",
  "severity": "info",
  "metadata": {
    "incident_id": 10,
    "playbook_id": "pb_notify",
    "execution_id": 123,
    "step_index": 1,
    "simulated": true,
    "executed": false
  }
}
```

Recommended event types:
- `incident_created`
- `incident_status_changed`
- `alert_linked`
- `alert_created`
- `playbook_execution_created`
- `playbook_execution_started`
- `playbook_execution_status_changed`
- `playbook_step_started`
- `playbook_step_completed`
- `playbook_step_failed`
- `playbook_step_skipped`
- `playbook_adapter_simulated`
- `approval_requested`
- `approval_approved`
- `approval_denied`
- `approval_expired`
- `approval_resumed`
- `audit_event`

Exact labels may follow existing API conventions, but event types should remain machine-readable and stable.

## Chronological ordering
Timeline entries should sort by timestamp ascending by default. If multiple events share the same timestamp, use deterministic secondary ordering:
- Incident events before alert events.
- Alert link events before playbook execution events.
- Playbook execution events before step events.
- Approval events after the step that requested them.
- Audit events last for the same timestamp unless directly tied to a specific lifecycle event.

If an event lacks a reliable timestamp, either omit it or include it in a separate `undated_events` array. Do not guess timestamps from unrelated records.

## Linked alerts
Include linked alert context in both the incident detail and timeline:
- Alert ID.
- Alert type.
- Severity.
- Source IP.
- Status if available.
- Created timestamp if available.
- Link timestamp from `incident_alerts` if available.

Alert timeline entries should use the alert timestamp for alert creation and the join-table timestamp for incident linking when those fields exist. If the join table lacks link timestamp, use a clear fallback or avoid claiming exact link time.

## Playbook executions
Include playbook executions where:
- `playbook_executions.incident_id = incident.id`, or
- `playbook_executions.alert_id` is one of the incident's linked alert IDs and the execution has no incident link.

The timeline should include:
- Execution created.
- Execution started.
- Execution completed or terminal status.
- Status and `last_completed_step`.
- `playbook_id`, execution ID, alert ID, and incident ID.

Do not mutate missing `incident_id` values while reading. If an execution is associated through linked alert fallback, report that relationship in metadata.

## Playbook steps log
Parse `steps_log` as structured JSON. Each entry should produce zero or more timeline events depending on available fields:
- Step action.
- Step index.
- Step status.
- Timestamp fields.
- Simulated adapter output.
- Approval-gate markers.
- Circuit breaker metadata if present.

If `steps_log` entry shapes vary across historical executions, parse defensively and preserve raw metadata as secondary detail. Malformed or unknown step entries should not break the endpoint; include a safe `playbook_step_event` with available metadata or omit the malformed entry with a logged warning.

## Approvals
Include approval requests linked to playbook executions and step indexes:
- Approval created/requested.
- Approval status.
- Decision timestamp.
- Expiration timestamp.
- Required role.
- Decision notes when safe to expose.

Include approval request events where available for a more precise approval timeline. These entries must be read-only and must not expire pending approvals as a side effect. GET routes must remain free of approval lifecycle mutation.

## Audit log events
Audit events may be included only when safely linked. Acceptable links include structured columns or JSON fields that explicitly reference:
- `incident_id`
- `alert_id`
- `playbook_execution_id`
- `approval_request_id`
- `queue_id`

If audit records are not structured enough for a safe join, omit them from the first implementation and document the limitation. Do not add brittle text matching.

## Frontend visibility
Frontend visibility is safe if it remains read-only and uses the backend timeline contract directly. The incident detail panel may add a "Timeline" section showing event type, time, source, and summary.

Frontend must not add:
- Approve/deny controls.
- Retry/resume/abandon controls.
- Queue run controls.
- Adapter/circuit breaker controls.
- Any mutation controls beyond existing incident status controls already present.

If UI scope feels large, implement backend first and leave frontend as a follow-up change.

## Auth and permissions
Use existing incident detail authorization:
- Analyst and super-admin users can view if they can currently view incidents.
- Viewer behavior should match current incident route behavior.
- Unauthenticated requests return existing unauthorized behavior.

Timeline visibility should not expose secrets, credentials, webhook URLs, or raw adapter configs.

## Safety boundaries
- Read-only.
- Visibility only.
- Must not execute or resume playbooks.
- Must not approve, deny, expire, or create approvals.
- Must not mutate incidents, alerts, approvals, queues, playbooks, playbook executions, metrics, circuit breakers, or integrations.
- Must preserve existing incident behavior.
- No real execution.
- No network calls.
- No subprocess execution.
- No daemon or scheduler.
- No queue changes.
- No ingest, detection, or correlation changes.

## Test strategy
Add backend tests that verify:
- Authenticated incident viewers can retrieve timeline data.
- Unauthenticated requests are rejected.
- Timeline includes linked alert events.
- Timeline includes playbook execution events for executions linked by `incident_id`.
- Timeline includes playbook execution events for linked-alert fallback when safe.
- Timeline includes parsed `steps_log` events.
- Timeline includes approval requests and approval request events linked to playbook executions.
- Timeline includes only safely linked audit events.
- Events are sorted chronologically with deterministic tie-breaking.
- Malformed or unknown `steps_log` entries do not break the endpoint.
- Timeline GET does not mutate incident, alert, approval, queue, playbook, execution, or audit tables.
- Timeline GET does not invoke playbook executor, queue worker, adapter execution, approval expiration, or integration code.

Frontend tests should be added only if frontend visibility is implemented in the same change.

## Risks and stop conditions
- Stop if timeline requires mutating records to create missing links.
- Stop if audit logs cannot be safely joined without text matching.
- Stop if approval timeline data would require expiring or recalculating approval state in a GET request.
- Stop if implementation needs executor, queue, integration, ingest, detection, or correlation changes.
- Stop if frontend scope introduces mutation controls or ambiguous real-remediation language.
