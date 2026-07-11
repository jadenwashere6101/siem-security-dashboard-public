## Why

The application swaps workspaces inside one persistent scrollable `<main>` element, so ordinary navigation inherits the previous workspace's scroll position while several View actions render details after long tables. Analysts can land mid-page or must scroll to find the record they selected, with inconsistent keyboard focus.

## What Changes

- **MAC AI:** Define one programmatic navigation request contract that distinguishes ordinary top-of-workspace navigation from intentional deep destinations.
- **MAC AI:** Reset the actual main scroll container for sidebar and ordinary programmatic navigation, while preserving filtered/deep destinations such as Recent Alerts and Response Registry context.
- **MAC AI:** Move Incident, Playbook definition/execution, and SOAR Operations details into a shared responsive adjacent-detail pattern with deterministic scroll and accessible focus.
- **MAC AI:** Cover SOC Command Center, sidebar, Response Registry, related-alert, and every affected `Open in…`/`View` transition with regression tests and visual/accessibility validation.
- Keep the current `activeSection` architecture; do not add React Router, backend routes, schema changes, or VM work.

## Capabilities

### New Capabilities

- `workspace-navigation-detail-ux`: Defines destination-aware workspace navigation, scroll/focus behavior, and responsive detail presentation.

### Modified Capabilities

- `cross-workspace-response-correlation`: Deep links into Response Registry and related-alert workflows retain their correlation context while using the shared destination contract.

## Impact

- Frontend: `App.js`, `SidebarLayout`, `Sidebar`, navigation utilities, SOC Command Center, Incidents, Playbooks, Dead Letters/SOAR Operations, Response Registry, Threat Hunt, Alerts, and related tests/styles.
- Backend/API/database/migrations/services: none.
- Deployment: Mac tests/build first; a later explicitly authorized frontend artifact deployment and UI smoke test only.

