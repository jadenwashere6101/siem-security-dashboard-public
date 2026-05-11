# Proposal: SOAR Incident Timeline Frontend

## Problem
The backend now exposes `GET /incidents/<incident_id>/timeline`, which returns a read-only enriched SOAR timeline for an incident. Incident detail still renders the existing incident and linked alert information, but the frontend does not yet show the timeline data that connects linked alerts, playbook execution events, step log events, approvals, and safely linked audit events.

Without frontend visibility, analysts must inspect separate panels or raw API responses to understand the sequence of SOAR activity associated with an incident.

## Goal
Add read-only frontend visibility for the enriched incident SOAR timeline.

## Scope
- Add a frontend service helper for `GET /incidents/<id>/timeline`.
- Display a read-only timeline inside the existing incident detail UI or a small dedicated section in the incident detail area.
- Show `timestamp`, `event_type`, `source`, `summary`, and safe metadata.
- Add loading, error, and empty states.
- Add focused frontend tests.
- Preserve existing incident detail and status-update behavior.

## Out of scope
- No implementation code in this change.
- No backend changes.
- No schema changes.
- No mutation controls.
- No approve, deny, resume, run, retry, cancel, reset, force-open, or circuit breaker controls.
- No executor changes.
- No SOAR queue changes.
- No integration behavior changes.
- No ingest, detection, or correlation changes.

## Success criteria
- Incident detail UI shows a read-only SOAR timeline when an incident is selected.
- Timeline fetch uses `GET /incidents/<id>/timeline`.
- Timeline entries render timestamp, event type, source, summary, and safe metadata.
- Loading, error, and empty states are clear and do not disrupt existing incident detail.
- UI does not imply real remediation occurred.
- UI does not expose secrets, raw adapter parameters, webhook URLs, credentials, or unsafe raw payloads.
- Tests prove no mutation controls were introduced.

## Why this is safe
The backend endpoint is read-only and already aggregates timeline data. The frontend change only renders that data for analyst/operator visibility. It does not introduce execution, approval, retry, queue, integration, or incident mutation behavior.
