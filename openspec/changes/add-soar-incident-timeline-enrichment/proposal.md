# Proposal: SOAR Incident Timeline Enrichment

## Problem
Incident detail currently provides incident and linked alert visibility, while SOAR playbook executions, playbook step logs, approval requests, and audit events are visible through separate surfaces. Analysts do not have a single read-only incident timeline that explains what SOAR activity happened around an incident.

The roadmap calls for a case timeline that joins alerts, playbooks, approvals, and audit activity. This should be implemented as visibility only, without changing incident creation, playbook execution, approval decisions, queue behavior, or any detection/correlation internals.

## Goal
Design a read-only enriched incident timeline that shows SOAR activity connected to an incident.

## Scope
- Extend incident detail or add a read-only incident timeline endpoint.
- Include linked alerts for the incident.
- Include `playbook_executions` connected to the incident.
- Include `steps_log` events from those playbook executions.
- Include `approval_requests` linked to playbook executions and playbook steps.
- Include `approval_request_events` where safely available.
- Include `audit_log` events only when they can be safely linked to the incident, alert, approval, or playbook execution.
- Normalize timeline entries with timestamps, event types, source object metadata, and chronological ordering.
- Add backend tests.
- Add frontend timeline visibility only if implementation confirms the backend contract is stable and the UI remains read-only.

## Out of scope
- No implementation code in this change.
- No real execution.
- No mutation controls.
- No playbook executor changes.
- No SOAR queue changes.
- No integration behavior changes.
- No ingest, detection, or correlation changes.
- No schema changes unless absolutely necessary and additive.
- No daemon or systemd worker.
- No approval or denial actions.
- No retry, resume, abandon, reset, or circuit breaker controls.

## Success criteria
- Incident detail can expose a chronological SOAR timeline without mutating data.
- Timeline entries include linked alerts, playbook executions, playbook step log events, linked approvals, and safely linked audit events.
- Entries include stable event types and timestamps.
- Timeline reads do not execute or resume playbooks.
- Timeline reads do not approve, deny, expire, or mutate approvals.
- Existing incident list/detail/status behavior remains unchanged.
- Backend tests prove timeline reads are read-only and do not touch queues, playbook execution state, approvals, alerts, or incidents.

## Why this is safe now
The underlying SOAR records already exist: incidents, linked alerts, playbook executions, step logs, approval requests, and audit entries. This change only designs a read-only aggregation layer over those records. It improves analyst context without increasing automation, external side effects, or remediation capability.
