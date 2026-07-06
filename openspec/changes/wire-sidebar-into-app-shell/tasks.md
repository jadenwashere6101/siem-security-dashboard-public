## 1. SidebarLayout Extension

- [ ] 1.1 Add an optional `topBarActions` prop to `frontend/src/components/SidebarLayout.js`, forwarded as `<TopBar>`'s `children`. This addition is approved.
- [ ] 1.2 Confirm the addition is backward compatible: existing `SidebarLayout` usage/tests that omit `topBarActions` are unaffected.
- [ ] 1.3 Add test coverage in `SidebarLayout.test.js` confirming `topBarActions` content renders inside `TopBar`'s slot.
- [ ] 1.4 Add an optional `eyebrow` prop to `frontend/src/components/TopBar.js` (rendered as a small label above `title`, mirroring the old "SIEM" eyebrow visual) and forward it through `SidebarLayout.js` via a matching optional `eyebrow` prop, so the eyebrow is not silently dropped.
- [ ] 1.5 Add test coverage in `TopBar.test.js` (and `SidebarLayout.test.js`) confirming `eyebrow` renders correctly and remains optional/backward compatible.
- [ ] 1.6 Scope ceiling: if preserving the eyebrow requires anything beyond a minimal optional prop plus one render line (e.g., restructuring `TopBar`'s layout, changing its title contract, or touching `Sidebar`), STOP and report instead of proceeding — falling back to dropping the eyebrow with a report is an acceptable outcome.
- [ ] 1.7 Make no other change to `SidebarLayout.js`, `Sidebar.js`, or `TopBar.js` beyond `topBarActions` and `eyebrow`.

## 2. App.js Integration Wiring

- [ ] 2.1 Import `SidebarLayout` in `App.js`.
- [ ] 2.2 Render `<SidebarLayout>` for the authenticated view with `sections={sectionsConfig}`, `roleFlags={roleFlags}`, `activeSectionId={activeSection}`, `onNavigate={setActiveSection}`, `title="SIEM Dashboard"`, `eyebrow="SIEM"` (unless task 1.6's scope ceiling was hit, in which case omit `eyebrow` and report).
- [ ] 2.3 Move the existing identity block (username + role badge) and logout button into `topBarActions`, with unchanged styling and unchanged `handleLogout` wiring.
- [ ] 2.4 Supply `statusLabel` and `versionLabel` from existing static data only (e.g., a static status string and the frontend `package.json` version) — no new feature, no backend call.
- [ ] 2.5 Do not add a new prop for `sessionNotice`; render it as the first child inside `SidebarLayout`'s `children`, above the content-switch block, with unchanged conditional logic and styling.

## 3. Content Preservation

- [ ] 3.1 Move the entire existing content-switch block (every panel and its `isSectionVisible` gating) into `SidebarLayout`'s `children`, unchanged.
- [ ] 3.2 Confirm no panel's props, gating condition, or mount/unmount behavior changed as part of the move.
- [ ] 3.3 Confirm `handleViewRelatedAlerts` (used by `ThreatHuntPanel`'s `onViewRelatedAlerts`) and `SocCommandCenter`'s `onNavigate={setActiveSection}` are unchanged and still call the same `setActiveSection`.

## 4. Removal of Obsolete Code

- [ ] 4.1 Remove the old inline header JSX (title/eyebrow, identity block wrapper, logout button wrapper, session-notice wrapper) now superseded by `SidebarLayout`/`topBarActions`/relocated `sessionNotice`.
- [ ] 4.2 Remove the old inline pill-nav JSX block now superseded by `Sidebar`.
- [ ] 4.3 Remove style constants that have zero remaining references after the above removals (expected: `sectionNavStyle`, `sectionTabStyle`, `activeSectionTabStyle`, `inactiveSectionTabStyle`, `headerStyle`, App.js's own `topBarStyle`, `sessionActionsStyle`, `pageStyle`, `containerStyle`, `eyebrowStyle`, `titleStyle`).
- [ ] 4.4 Before deleting any style constant, confirm it has no remaining reference (e.g., `sessionNoticeStyle`, `identityBlockStyle`, `identityLabelStyle`, `roleBadgeStyle` and its role variants, and `logoutButtonStyle` must NOT be deleted — they are still used inside `topBarActions`).
- [ ] 4.5 Do not modify, remove, or rename anything else in `App.js` (alert filtering/sorting helpers, metrics/chart builders, auth flow, panel props).

## 5. Tests

- [ ] 5.1 Run `App.test.js` unmodified and confirm it passes; its role/name-based nav queries should be satisfied by `Sidebar`'s rendered buttons.
- [ ] 5.2 If a genuine incompatibility is found, adapt `App.test.js` minimally and report exactly what changed and why — do not silently rewrite its assertions.
- [ ] 5.3 Run the full frontend test suite (`npm test -- --watchAll=false`) and confirm no regressions.
- [ ] 5.4 Run `npm run build` and confirm it compiles without introducing new warnings beyond the project's existing baseline.

## 6. Manual Verification

- [ ] 6.1 Log in as `viewer`: confirm only permitted sections appear in the sidebar, identity/role/logout render correctly in `TopBar`, and no restricted content renders.
- [ ] 6.2 Log in as `analyst`: confirm the correct broader section set appears and each is reachable.
- [ ] 6.3 Log in as `super_admin`: confirm all sections appear, including `administration` and `soar-queue`.
- [ ] 6.4 Confirm login and logout flows are visually and behaviorally unchanged.
- [ ] 6.5 Confirm the 5-second alert polling interval continues to run in the background regardless of which section is active.
- [ ] 6.6 Confirm active-item highlighting follows sidebar clicks.
- [ ] 6.7 Confirm programmatic navigation (`ThreatHuntPanel` → Dashboard via related-alerts, `SocCommandCenter`'s internal navigation) updates the sidebar highlight correctly.
- [ ] 6.8 Confirm the sidebar collapse/expand hamburger toggle works and nav items remain accessible-by-name while collapsed.
- [ ] 6.9 Confirm `TopBar` correctly shows identity, role badge, and that the logout button still logs out.
- [ ] 6.10 Confirm no URL/history/routing behavior was introduced (single URL throughout).

## 7. Final Validation

- [ ] 7.1 Run `openspec validate wire-sidebar-into-app-shell --strict` and record the result.
- [ ] 7.2 Run `git diff --check`.
- [ ] 7.3 Confirm `package.json`/lockfile are unchanged and no new npm dependency was added.
