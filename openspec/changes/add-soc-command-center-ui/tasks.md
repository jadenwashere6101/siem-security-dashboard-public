## 1. Frontend Audit and Data Contract

- [ ] 1.1 Audit `frontend/src/App.js` navigation, role gating, section styles, and existing SOAR tab placement.
- [ ] 1.2 Audit existing services for usable read-only data: alerts, incidents, approvals, dead letters, notification deliveries, playbooks/executions, worker metrics, queue status, and integration status.
- [ ] 1.3 Document any tiny read-only service helper gap discovered during implementation; do not add backend endpoints unless the Command Center cannot render safely without it.

## 2. Command Center Data Model

- [ ] 2.1 Create local normalization helpers for counts, status severity, activity feed events, attention items, and integration safety labels.
- [ ] 2.2 Implement per-source loading/error/data handling so one failed or forbidden API does not blank the whole Command Center.
- [ ] 2.3 Add safe fallback shapes for missing or unexpected API responses.
- [ ] 2.4 Ensure no helper includes credentials, webhook URLs, SMTP values, auth headers, raw payloads, or raw provider responses.

## 3. SOC Command Center Component

- [ ] 3.1 Create `frontend/src/components/SocCommandCenter.js`.
- [ ] 3.2 Add the landing summary card grid: SOC status, incident pressure, active automations, pending approvals, dead-letter pressure, notification health, worker health, and integration safety.
- [ ] 3.3 Add the global activity feed with recent incidents, playbook executions, approvals, dead letters, notification failures, queue/worker events when available, and safe unavailable-source markers.
- [ ] 3.4 Add the “What needs attention?” panel for stale/running executions, retrying/open dead letters, pending approvals, failed playbooks, notification failures, and queue pressure.
- [ ] 3.5 Add the incident workspace with selectable incidents, summary, timeline, linked alerts when available, and linked SOAR context where existing APIs support it.
- [ ] 3.6 Add empty, loading, and error states for each major region.
- [ ] 3.7 Add compact, responsive styles with stable dimensions, status badges, timeline rows, and narrow-width readability.

## 4. App Wiring and Role Safety

- [ ] 4.1 Add a new top-level `SOC Command Center` tab to `App.js` using the existing `activeSection` pattern.
- [ ] 4.2 Pass required props such as alerts, role, username, and safe navigation callbacks into `SocCommandCenter`.
- [ ] 4.3 Preserve existing Dashboard, SOAR Operations, SOAR Metrics, Integrations, Incidents, Approvals, Playbooks, Queue, and Admin tabs unchanged.
- [ ] 4.4 Hide analyst-only operational controls from viewer/auditor roles and avoid adding new mutation buttons.
- [ ] 4.5 Clearly label simulation, real-enabled, blocked, and unavailable integration safety states.

## 5. Tests

- [ ] 5.1 Add `frontend/src/components/SocCommandCenter.test.js`.
- [ ] 5.2 Test summary cards render from mocked existing services.
- [ ] 5.3 Test activity feed combines multiple event types and sorts by recency.
- [ ] 5.4 Test unavailable or failing source APIs degrade locally without blanking the whole view.
- [ ] 5.5 Test attention panel prioritizes pending approvals, open/retrying dead letters, failed playbooks, notification failures, queue pressure, and stale/running executions.
- [ ] 5.6 Test incident selection renders incident workspace context.
- [ ] 5.7 Test viewer/auditor role does not show analyst-only operational controls.
- [ ] 5.8 Test simulation/real-mode safety labels render without exposing secrets.
- [ ] 5.9 Update `App.test.js` or add focused navigation coverage so the new tab is reachable and existing tabs remain intact.

## 6. Verification

- [ ] 6.1 Run `CI=true npm test -- --watchAll=false SocCommandCenter.test.js`.
- [ ] 6.2 Run `CI=true npm test -- --watchAll=false App.test.js`.
- [ ] 6.3 Run existing affected frontend suites as needed: `IncidentsPanel`, `ApprovalsPanel`, `DeadLettersPanel`, `SoarMetricsDashboard`, `IntegrationStatusPanel`, and service tests touched by implementation.
- [ ] 6.4 Run `npm run build` from `frontend/`.
- [ ] 6.5 Run `git diff --check`.
- [ ] 6.6 Confirm no backend, schema, VM/runtime, env var, ingest, detection, correlation, or real-integration behavior changed.
