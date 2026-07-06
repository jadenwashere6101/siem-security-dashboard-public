## Why

An architecture audit for the upcoming sidebar navigation redesign found that `frontend/src/App.js` currently defines section navigation and role-gating in two separate, duplicated places: the inline pill-button nav block (~lines 461-608) and the inline content-switch block (~lines 610-797). Each of the 12 sections has its visibility condition (`canTakeAlertActions`, `isSuperAdmin`, etc.) written out twice. This duplication is the main identified risk for the sidebar redesign: if the two copies ever drift, a nav item could be shown with no matching content, or a section could render without a corresponding nav entry.

Before building any new sidebar shell, this change extracts a single `sectionsConfig` source of truth so both nav rendering and content gating read from the same data, removing the drift risk ahead of time and giving the later sidebar work one clean data source to consume.

## What Changes

- Add `frontend/src/utils/sectionsConfig.js` defining all 12 existing sections (`dashboard`, `soc-command-center`, `blocklist`, `threat-hunt`, `administration`, `soar-queue`, `soar-incidents`, `soar-approvals`, `soar-playbooks`, `soar-playbook-metrics`, `soar-integrations`, `soar-operations`) with `id`, `label`, `group`, and `visibleWhen(roleFlags)`.
- Refactor `App.js`'s existing nav-button block to render by iterating `sectionsConfig` instead of one hardcoded button per section.
- Refactor `App.js`'s existing content-switch block to gate on the same `sectionsConfig` entries instead of separate inline conditions.
- Preserve the exact current pill-style navigation UI, button order, labels, and click behavior — this is a data/logic refactor only.

## Capabilities

### New Capabilities
- `section-nav-config`: a single source of truth for section id/label/group/role-visibility, consumed by both navigation rendering and content gating.

### Modified Capabilities
- None. Existing dashboard navigation behavior is preserved exactly; no user-visible capability changes.

## Impact

- Frontend only: new `frontend/src/utils/sectionsConfig.js` and `frontend/src/utils/sectionsConfig.test.js`; internal refactor of `frontend/src/App.js` (no new components, no layout changes).
- No backend, schema, routing, or URL changes.
- No changes to any panel component (`DashboardSection`, `SocCommandCenter`, `BlocklistManagerPanel`, etc.) — they continue to be rendered exactly as before.
- `App.test.js` is expected to require no modification; it is the primary regression guard for this change.
- This change is a prerequisite for the later sidebar shell specs (`build-sidebar-shell-components`, `wire-sidebar-into-app-shell`) but does not itself introduce any sidebar, hamburger, or layout shell UI.
