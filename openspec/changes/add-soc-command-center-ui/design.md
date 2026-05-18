## Context

The app already has a mature SOAR backend and several focused frontend panels: Incidents, Approvals, SOAR Queue, Playbooks, Integrations, SOAR Metrics, and SOAR Operations. Each panel is useful, but operators must switch tabs to answer the basic command-center question: what is happening right now, what needs attention, and is automation safe.

The current React app uses functional components, local services under `frontend/src/services/`, and section-based navigation in `App.js`. Existing SOAR sections are mostly gated to analyst/super_admin roles. The Command Center should fit this architecture rather than replace it.

## Goals / Non-Goals

**Goals:**
- Add one polished `SocCommandCenter` frontend component as a new top-level tab.
- Aggregate existing read-only API data into summary cards, global activity feed, attention panel, and incident workspace.
- Reuse current services first: `metricsService`, `incidentService`, `approvalService`, `deadLetterService`, `notificationDeliveryService`, `playbookService`, `soarQueueService`, `integrationService`, and existing alert loading.
- Keep existing SOAR Operations and SOAR Metrics tabs intact.
- Provide clear simulation/real-mode labels and integration safety posture without exposing secrets.
- Provide role-aware controls: analyst/super_admin may see existing safe action links; viewer/auditor must not see analyst-only mutation controls.
- Support missing/forbidden APIs with per-source fallback states so one failed endpoint does not blank the whole Command Center.

**Non-Goals:**
- No schema/migration changes.
- No new backend execution semantics.
- No real integration calls.
- No new mutation buttons unless backed by existing safe APIs and existing role checks.
- No global frontend architecture rewrite or route framework migration.
- No replacement of existing SOAR Operations, Metrics, Integrations, Approvals, Playbooks, Incidents, or Dashboard tabs.

## Decisions

### Decision 1: Frontend-only aggregation first

Implement the Command Center as a React aggregation surface that calls existing services concurrently and normalizes results in component-local helpers.

Rationale: The existing backend already exposes the necessary operational read models in separate endpoints. A frontend aggregator keeps this change implementable in one large frontend-focused batch and avoids creating a new backend contract before real usage proves a gap.

Alternatives considered:
- Add a backend `/soc-command-center` aggregation endpoint. This would reduce frontend request fan-out but introduces backend scope, test surface, and likely future schema pressure.
- Rebuild existing SOAR panels into a new app shell. This would be higher risk and unnecessary.

### Decision 2: One component with small pure helper functions

Create `frontend/src/components/SocCommandCenter.js` with pure helpers for normalization, counting, feed construction, attention item derivation, and status severity. Tests should exercise these via rendered behavior and exported helpers only if local patterns support it.

Rationale: A single component keeps the implementation batch cohesive. Pure helpers keep the data-shaping logic testable without adding a new state management pattern.

Alternatives considered:
- Multiple new components from the start. This may be cleaner long term but risks overbuilding before the UI shape settles.

### Decision 3: Add navigation without changing app architecture

Wire a new top-level tab into `App.js`, likely near the existing SOAR sections, using the same `activeSection` pattern and role gating. Preserve existing labels and components.

Rationale: This respects current architecture and keeps the change reviewable.

Alternatives considered:
- Introduce React Router or a nested SOAR shell. That is a global rewrite and out of scope.

### Decision 4: Role model follows existing frontend behavior

Analyst and super_admin users can see the full Command Center. Viewer/auditor behavior should either show read-only posture content without mutation controls or follow the existing restricted-section message pattern if current app conventions require it.

Rationale: The user asked for viewer/auditor not to see analyst-only operational controls, not for new authorization semantics.

Alternatives considered:
- Hide the whole Command Center from viewers. This is safe but may lose useful read-only posture visibility.

### Decision 5: Safe fallback per source

Each data source should track `loading`, `error`, and `data` independently. The summary and feed should use available data and label unavailable sources instead of failing the whole view.

Rationale: Operational consoles are most useful during partial failure. Existing APIs may be role-limited or unavailable in development, and the UI should remain informative.

## Data Sources and Expected Reuse

- Alerts: existing `loadAlerts()` and the `alerts` already held in `App.js`.
- Incidents: `loadIncidents()`, `loadIncidentDetail()`, `loadIncidentTimeline()`.
- Playbooks/executions: `listPlaybooks()`, `listPlaybookExecutions()`, `getPlaybookExecution()`.
- Approvals: `listApprovals()`, optionally `getApproval()` for existing detail links.
- Dead letters: `getDeadLetters()`, `getDeadLetterMetrics()`.
- Notification delivery: `listNotificationDeliveries()`, `getNotificationDeliveryMetrics()`.
- Worker health: `getPlaybookWorkerMetrics()`, `loadSoarQueueStatus()`, `loadRecentSoarQueueItems()`.
- Integration safety: `getIntegrationStatus()`.
- Metrics: `getIncidentMetrics()`, `getPlaybookMetrics()`, `getApprovalMetrics()`, notification/dead-letter metrics.

If an endpoint returns a shape that differs from expectations, the component should normalize defensively and display an unavailable/empty state for that source.

## UI Shape

The first viewport should be the operational console itself, not a marketing or explanatory page.

Recommended layout:
- Header band: “SOC Command Center”, role label, global safety badge, last refreshed timestamp, refresh button.
- Status summary grid: incident pressure, automations, approvals, dead letters, notifications, worker health, integration safety.
- Main work area:
  - Left/primary: global activity feed with timeline rows grouped by newest first.
  - Right/secondary: “What needs attention?” panel with prioritized items and safe navigation affordances.
- Incident workspace: selectable incident list/detail region below or beside feed depending on width.

Visual style should stay dense, utilitarian, and consistent with the existing dark dashboard. Use compact cards, badges, restrained color, responsive grid/flex layouts, and no decorative landing-page elements.

## Risks / Trade-offs

- Fan-out requests could be noisy or slow → Fetch concurrently, keep limits small, and render partial data.
- Endpoint shape drift could break feed aggregation → Normalize defensively and add tests for missing/empty/error data.
- Command Center could duplicate existing tabs → Use it as a summary and launchpad, not a replacement for detailed panels.
- Role-aware controls could accidentally expose actions → Default to read-only links; add tests for viewer/auditor control hiding.
- Missing incident linkage may limit workspace richness → Show available incident/timeline data and label unavailable linked context without backend changes.
- Visual density could hurt narrow screens → Use responsive constraints, small headings, stable card dimensions, and mobile-friendly stacking.

## Migration Plan

1. Add `SocCommandCenter.js` and tests.
2. Wire new tab into `App.js` without removing existing tabs.
3. Reuse existing services; add only tiny read-only service helpers if an existing endpoint lacks a wrapper.
4. Run frontend focused tests and build.
5. Rollback is removing the new tab/component/service helper changes; no backend or schema rollback is expected.
