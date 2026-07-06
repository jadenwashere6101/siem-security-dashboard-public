## 1. Audit and Parity Table

- [ ] 1.1 Re-confirm the exact current role-gating condition for each of the 12 sections in both the nav block (`App.js` ~461-608) and the content block (`App.js` ~610-797).
- [ ] 1.2 Document the id/label/group/gating parity table (one row per section) before writing `sectionsConfig.js`, so the port can be checked against it.
- [ ] 1.3 Confirm no section ids exist beyond the 12 listed: `dashboard`, `soc-command-center`, `blocklist`, `threat-hunt`, `administration`, `soar-queue`, `soar-incidents`, `soar-approvals`, `soar-playbooks`, `soar-playbook-metrics`, `soar-integrations`, `soar-operations`.
- [ ] 1.4 If the parity audit finds that the existing nav-block condition and content-block condition already disagree for any section, stop and report the mismatch before writing `sectionsConfig.js`. Do not silently choose one side as authoritative.

## 2. sectionsConfig Implementation

- [ ] 2.1 Create `frontend/src/utils/sectionsConfig.js` exporting an array of 12 entries: `{ id, label, group, visibleWhen(roleFlags) }`.
- [ ] 2.2 Implement `visibleWhen` for each entry as an exact 1:1 port of the parity table from Task 1 — no reinterpretation of existing role logic.
- [ ] 2.3 Do not introduce new role flags, new groups, or new visibility rules beyond what already exists today.
- [ ] 2.4 Add `frontend/src/utils/sectionsConfig.test.js` asserting `visibleWhen` output for representative role-flag combinations (super_admin, analyst, viewer, unauthenticated/no-role) against all 12 sections.

## 3. App.js Nav Consumption

- [ ] 3.1 Refactor the inline nav-button block to render by mapping over `sectionsConfig`, calling `visibleWhen(roleFlags)` per entry to decide visibility.
- [ ] 3.2 Preserve exact button text, order, styling, and `setActiveSection` click behavior.
- [ ] 3.3 Remove the now-duplicated inline nav visibility conditions.

## 4. App.js Content Gating Consumption

- [ ] 4.1 Refactor the content-switch block to gate on the same `sectionsConfig` entries (directly or via a shared lookup) instead of separate inline conditions.
- [ ] 4.2 Preserve exact panel rendering, prop passing, and mount/unmount behavior for every section.
- [ ] 4.3 Remove the now-duplicated inline content-gating conditions.

## 5. Tests

- [ ] 5.1 Run existing `App.test.js` unmodified and confirm it passes with no changes required.
- [ ] 5.2 Run new `sectionsConfig.test.js` and confirm role-visibility parity with the original 12-section table.
- [ ] 5.3 Run the full frontend test suite and confirm no regressions.

## 6. Verification

- [ ] 6.1 Manually diff `App.js` before/after to confirm no visible UI/style/order change.
- [ ] 6.2 Confirm no sidebar, hamburger, layout shell, routing, or URL behavior was introduced.
- [ ] 6.3 Manually smoke-test the pill navigation in a browser for each tested role (super_admin, analyst, viewer) and confirm it looks and behaves identically to before this change, before any sidebar work begins.
- [ ] 6.4 Run `openspec validate extract-section-nav-config --strict` and record the result.
