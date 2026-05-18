## Why

The SOAR platform now has mature execution, safety, audit, retry, and observability foundations, but operators still have to move across several separate tabs to understand what needs attention. A SOC Command Center gives analysts and super admins one polished operational console for incident pressure, automation health, approval load, dead-letter risk, notification health, worker status, and integration safety.

## What Changes

- Add a new SOC Command Center top-level frontend experience that uses existing APIs and services first.
- Present a compact landing view with high-level SOC status, incident pressure, active automations, pending approvals, dead-letter pressure, notification health, worker health, and integration safety state.
- Add a global activity feed combining recent incidents, playbook executions, approvals, dead letters, notification failures, and worker/recovery signals when available.
- Add an incident-focused workspace for selected incident summary, linked alerts, linked executions/playbooks, approvals, dead letters, notifications, and existing safe incident context.
- Add an operational “What needs attention?” panel for stale/running executions, retrying/open dead letters, pending approvals, failed playbooks, notification failures, and queue pressure.
- Preserve existing SOAR Operations, SOAR Metrics, Integrations, Approvals, Playbooks, and Incidents views.
- Keep implementation frontend-first; no schema changes, no new execution semantics, and no real integrations triggered.

## Capabilities

### New Capabilities
- `soc-command-center-ui`: A role-aware SOC Command Center dashboard that aggregates existing SIEM/SOAR operational state into a single polished console.

### Modified Capabilities
- None.

## Impact

- Frontend React code: `frontend/src/App.js`, a new `SocCommandCenter` component, focused tests, and optional small service helpers that wrap existing read-only endpoints.
- Existing frontend services expected to be reused: incidents, approvals, dead letters, metrics, integration status, notification delivery, playbooks/executions, SOAR queue, and alerts.
- Backend/API impact should be none unless implementation discovers a tiny read-only field gap that blocks the UI.
- No database schema/migration changes, no VM/runtime actions, no new mutation behavior, and no real outbound integrations.
