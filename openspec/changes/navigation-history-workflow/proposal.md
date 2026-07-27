## Why

Analysts currently lose investigation context when moving between SIEM workspaces, pivots, and detail views. A lightweight workspace history will let analysts move backward and forward through an investigation flow without rebuilding filters, selections, or scroll context.

## What Changes

- Add an analyst-facing workspace history system with Back and Forward controls in the application header.
- Capture meaningful investigation navigation entries for workspace changes, alert/incident/source/recon pivots, and supported detail selections.
- Restore enough UI state to continue investigations: active workspace, selected entities, relevant filters/search/sort/pagination, selected tabs/views, expanded alert rows, and practical scroll position.
- Integrate browser Back/Forward with the workspace history through `pushState`/`popstate` while keeping the current single-page React architecture.
- Keep history lightweight by storing only serializable metadata needed to reconstruct UI state, not API result datasets or large payloads.
- Clear or reset history at safe lifecycle boundaries such as login/logout, role visibility changes, and explicit default landing resets.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `workspace-navigation-detail-ux`: Add investigation workspace history, state restoration, top-bar Back/Forward controls, and browser Back/Forward integration.

## Impact

- Frontend-only change centered on `App.js`, `SidebarLayout`, `TopBar`, `workspaceNavigation` helpers, and affected workspace panels that expose selected IDs, filters, tabs, pagination, or scroll restoration hooks.
- No backend API, database, RBAC, SOAR, AI, ingest, or deployment architecture changes.
- Tests should cover stack behavior, state restoration, browser history integration, button disabled states, and representative cross-workspace investigation pivots.
