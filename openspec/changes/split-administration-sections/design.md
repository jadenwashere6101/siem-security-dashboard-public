## Context

The live sidebar navigation consumes `frontend/src/utils/sectionsConfig.js` and groups visible items by each entry's `group` field. Today that config contains one `administration` entry labeled `Administration`, grouped under `administration`, with `visibleWhen: ({ isSuperAdmin }) => isSuperAdmin`.

`frontend/src/App.js` currently checks `activeSection === "administration"` and, when visible, renders three existing panels in one fragment: `DetectionRulesPanel`, `AdminUsersPanel`, and `AuditLogPanel`. This creates an overloaded section where unrelated administrative workflows are coupled by a single active section id. The app remains a single-URL React SPA with `activeSection` state in `App.js`; this design keeps that model.

## Goals / Non-Goals

**Goals:**
- Split the bundled Administration page into three first-class sidebar items under the existing Administration group.
- Add stable section ids for detection rules, user management, and audit logs.
- Render exactly one existing administrative panel for each new section.
- Preserve the current super-admin-only access behavior for all three new items.
- Keep the sidebar group named Administration and avoid a separate Configurables group.
- Keep the implementation frontend-only and scoped to navigation configuration, content switching, and tests.

**Non-Goals:**
- No new admin features, form behavior, audit-log behavior, or detection-rule behavior.
- No backend APIs, database changes, role model changes, or authorization semantics changes.
- No React Router, URL routes, route params, deep-linking, or browser history changes.
- No visual redesign, sidebar shell rewrite, panel rewrite, or new dependencies.
- No Administration overview page unless a future requirement explicitly justifies one.

## Decisions

### Decision 1: Replace the old Administration section entirely

Use option A: replace the old `administration` section with the three new sections. Do not keep an Administration overview section.

Rationale: the current Administration destination is not a distinct workflow; it is only a container for three unrelated panels. Keeping it alongside the three targeted items would preserve the overloaded page, create duplicate access paths, complicate content-switch tests, and make the active sidebar state less meaningful. A clean split gives each workflow one obvious nav target while still preserving the Administration group heading.

Alternative considered: keep an `Administration` overview plus `Detection Rules`, `Users`, and `Audit Logs`. Rejected because there is no current overview component, no requested overview content, and adding one would either duplicate the old bundled behavior or create a new feature outside this scope.

### Decision 2: Use explicit section ids tied to workflows

Add these ids to `sectionsConfig`:

- `detection-rules`
- `admin-users`
- `admin-audit-logs`

All three entries use `group: "administration"` and labels `Detection Rules`, `Users`, and `Audit Logs`. The ids are intentionally stable, descriptive, and not route-like. The `admin-` prefix is used for users and audit logs to avoid collisions with possible future non-admin users or audit views; detection rules is already domain-specific enough without the prefix.

Alternative considered: ids such as `administration-detection-rules`, `administration-users`, and `administration-audit-logs`. Rejected as unnecessarily verbose for internal SPA state, though acceptable if implementation discovers a local naming convention that strongly favors group-prefixed ids.

### Decision 3: Preserve role gating exactly

Each new Administration-group item must use the same visibility predicate as the existing bundled section: `visibleWhen: ({ isSuperAdmin }) => isSuperAdmin`, unless implementation auditing shows the live code has already changed to a different gate before work begins. Viewer and analyst users must not see any of the three admin items, and super admins must see all three.

This only controls frontend visibility. It does not replace or weaken any backend authorization that existing panel APIs already rely on.

### Decision 4: Split content rendering without rewriting panels

`App.js` should replace the single bundled `activeSection === "administration"` block with three independent blocks:

- `activeSection === "detection-rules"` renders only `DetectionRulesPanel`.
- `activeSection === "admin-users"` renders only `AdminUsersPanel`.
- `activeSection === "admin-audit-logs"` renders only `AuditLogPanel`.

Each block must keep the same `isSectionVisible(sectionId, roleFlags)` guard pattern used by the rest of the content switch. Existing panel imports, props, styles, internal fetching, and behavior remain unchanged.

### Decision 5: Preserve the single-URL sidebar model

This change must continue using `activeSection` in `App.js` as the source of truth. Sidebar clicks still call `setActiveSection(section.id)` through the existing sidebar shell. No URLs, router state, deep links, route constants, or history entries are introduced.

## Navigation Model

The Administration group should render these visible items for super admins, in this order:

1. Detection Rules
2. Users
3. Audit Logs

The group label remains Administration because `Sidebar` renders group names from the `group` value. The spec does not require changing the underlying group key from `administration`; any display casing behavior remains owned by the existing sidebar shell.

Viewer and analyst users should see no Administration group if these are the only visible entries in that group.

## Section ID Strategy

The previous `administration` id is retired from normal navigation and rendering for this workflow. The new ids are workflow-specific and map one-to-one to existing panels:

- `detection-rules` -> `DetectionRulesPanel`
- `admin-users` -> `AdminUsersPanel`
- `admin-audit-logs` -> `AuditLogPanel`

Implementation should update tests that assert the exact section-id list from 12 sections to 14 sections, replacing `administration` with the three new ids and preserving the relative position before the SOAR group.

## Role-Gating Strategy

All three entries inherit the current super-admin-only gate. The implementation should update `sectionsConfig.test.js` role matrices so:

- `super_admin` can see `detection-rules`, `admin-users`, and `admin-audit-logs`.
- `analyst`, `viewer`, and unauthenticated role flag sets cannot see them.

No role names, role flags, permission derivation, or backend authorization checks change.

## Scope

In scope:
- Update `sectionsConfig` to define three Administration-group entries.
- Update `sectionsConfig` unit tests for id list, count, order, labels/groups if covered, and visibility matrix.
- Update `App.js` content switching to render one matching existing panel for each new id.
- Add or adapt `App.test.js` coverage only where needed to verify admin item visibility and per-panel rendering.
- Run the validation commands and perform the manual browser checks listed in the validation plan.

Expected files:
- `frontend/src/utils/sectionsConfig.js`
- `frontend/src/utils/sectionsConfig.test.js`
- `frontend/src/App.js`
- `frontend/src/App.test.js` if needed

Out of scope:
- Any application source changes beyond the expected frontend files required for this split.
- New components, new panel props, new APIs, new dependencies, routing, deep-linking, visual redesign, backend changes, or commits.

## Acceptance Criteria

- The sidebar Administration group contains `Detection Rules`, `Users`, and `Audit Logs` for super admins.
- The old bundled `Administration` nav item is not present as a normal sidebar item after the split.
- `Detection Rules` activates only the `DetectionRulesPanel` content.
- `Users` activates only the `AdminUsersPanel` content.
- `Audit Logs` activates only the `AuditLogPanel` content.
- Viewer and analyst users cannot see the three Administration items.
- Super admins can see all three Administration items.
- Existing sidebar shell behavior, grouping, collapse behavior, and active-section highlighting continue to work.
- The app remains a single-URL SPA with no React Router, URL route, deep-link, or history behavior added.
- Existing panels are preserved rather than rewritten.
- No backend, dependency, or role model files are changed.

## Validation Plan

Automated validation:
- Run `npm test -- --watchAll=false`.
- Run `npm run build`.
- Run `openspec validate split-administration-sections --strict`.
- Run `git diff --check`.

Manual browser verification:
- Administration group contains the new items.
- Detection Rules opens only `DetectionRulesPanel`.
- Users opens only `AdminUsersPanel`.
- Audit Logs opens only `AuditLogPanel`.
- Viewer and analyst users cannot see these admin items.
- Super admin can see all three.
- No routing changes occur when navigating between the items.
- Existing sidebar behavior still works, including active state and collapse/expand behavior.

## Risks / Trade-offs

- **Tests that assume 12 sections fail** -> Update only the relevant expected id/count/visibility fixtures to the new 14-section model.
- **Old `administration` id referenced elsewhere** -> Audit with `rg` before editing and update only references tied to the bundled admin page; unrelated historical docs or archived specs do not need source changes.
- **Role visibility drift** -> Keep all three new entries on the exact existing `isSuperAdmin` predicate and cover it in `sectionsConfig.test.js`.
- **Panel prop regression** -> Move each existing panel JSX block intact into its own content condition, preserving props and style objects.
- **Accidental scope creep into routing or redesign** -> Treat any router, URL, shell rewrite, or visual redesign need as out of scope and stop for clarification.
- **Retiring the old id affects default state** -> The current default active section is `dashboard`, so removing the old admin id from normal rendering should not affect initial load. If any programmatic navigation still targets `administration`, update that caller only if it is part of the current admin split; otherwise report it.

## Migration Plan

1. Audit current `administration` references in frontend source and tests.
2. Replace the single `administration` config entry with the three new Administration-group entries.
3. Update the content switch in `App.js` so each new id renders exactly one existing panel.
4. Update focused tests for section ids, role visibility, and admin navigation behavior.
5. Run automated validation and manual browser verification.
6. Rollback is reverting the frontend source/test changes from this spec; there is no backend, data, route, or dependency migration to unwind.
