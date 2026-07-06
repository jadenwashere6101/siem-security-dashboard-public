## 1. Audit Current Administration Wiring

- [x] 1.1 Search frontend source and tests for `administration`, `DetectionRulesPanel`, `AdminUsersPanel`, and `AuditLogPanel` references.
- [x] 1.2 Confirm the live Administration visibility predicate is still super-admin-only before changing tests or config.
- [x] 1.3 Confirm there are no programmatic navigation callers that require preserving the old `administration` section id.

## 2. Update Section Configuration

- [x] 2.1 Replace the single `administration` section entry with `detection-rules`, `admin-users`, and `admin-audit-logs`.
- [x] 2.2 Set all three new entries to `group: "administration"` and labels `Detection Rules`, `Users`, and `Audit Logs`.
- [x] 2.3 Preserve the existing super-admin-only `visibleWhen` predicate for all three entries.

## 3. Update Content Rendering

- [x] 3.1 Replace the bundled `activeSection === "administration"` block in `App.js` with a `detection-rules` block that renders only `DetectionRulesPanel`.
- [x] 3.2 Add an `admin-users` block that renders only `AdminUsersPanel` with its existing props.
- [x] 3.3 Add an `admin-audit-logs` block that renders only `AuditLogPanel` with its existing props.
- [x] 3.4 Keep the existing `isSectionVisible(sectionId, roleFlags)` guard pattern for each new block.
- [x] 3.5 Verify no route, URL, React Router, backend, dependency, panel rewrite, or sidebar shell redesign changes were introduced.

## 4. Update Tests

- [x] 4.1 Update `sectionsConfig.test.js` expected ids, count, ordering, and role-visibility matrix for the new 14-section model.
- [x] 4.2 Add or adjust tests to confirm viewer and analyst users cannot see the new Administration items.
- [x] 4.3 Add or adjust super-admin navigation tests so each new item renders only its matching panel.
- [x] 4.4 Keep test changes focused on the split; do not rewrite unrelated App or sidebar tests.

## 5. Validation

- [x] 5.1 Run `npm test -- --watchAll=false`.
- [x] 5.2 Run `npm run build`.
- [x] 5.3 Run `openspec validate split-administration-sections --strict`.
- [x] 5.4 Run `git diff --check`.
- [x] 5.5 Manually verify the Administration group contains `Detection Rules`, `Users`, and `Audit Logs` for super admins.
- [x] 5.6 Manually verify `Detection Rules` opens only `DetectionRulesPanel`.
- [x] 5.7 Manually verify `Users` opens only `AdminUsersPanel`.
- [x] 5.8 Manually verify `Audit Logs` opens only `AuditLogPanel`.
- [x] 5.9 Manually verify viewer and analyst users cannot see these admin items.
- [x] 5.10 Manually verify there are no routing changes and existing sidebar behavior still works.
