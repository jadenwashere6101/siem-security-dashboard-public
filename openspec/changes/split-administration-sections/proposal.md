## Why

The sidebar navigation now exposes grouped sections, but Administration is still a single overloaded destination that mounts detection rule configuration, admin user management, and audit logs together. Super-admin users need direct, predictable entry points for each administrative workflow without changing routes, roles, APIs, or panel implementations.

## What Changes

- Replace the current single `administration` sidebar item with three separate Administration-group items:
  - `detection-rules` labeled `Detection Rules`
  - `admin-users` labeled `Users`
  - `admin-audit-logs` labeled `Audit Logs`
- Keep the sidebar group name as `administration` / Administration and do not create a new Configurables group.
- Preserve the current super-admin-only gating used by the bundled Administration item unless implementation discovers a different existing gate in code.
- Update authenticated content rendering so each new section mounts only its matching existing panel:
  - `DetectionRulesPanel`
  - `AdminUsersPanel`
  - `AuditLogPanel`
- Preserve the single-URL SPA model, sidebar shell behavior, existing panel props, existing role model, frontend-only scope, and dependency set.
- Remove the old bundled Administration destination from normal navigation instead of keeping it as an overview.

## Capabilities

### New Capabilities

- `admin-section-navigation`: Defines separate sidebar navigation and content-rendering behavior for Detection Rules, Users, and Audit Logs under the Administration group.

### Modified Capabilities

- None.

## Impact

- Affected frontend files are expected to include `frontend/src/utils/sectionsConfig.js`, `frontend/src/utils/sectionsConfig.test.js`, `frontend/src/App.js`, and possibly `frontend/src/App.test.js`.
- No backend APIs, database schema, URL routes, React Router integration, dependencies, panel rewrites, visual redesign, or role model changes are in scope.
