## 1. sidebarPreference Utility

- [ ] 1.1 Create `frontend/src/utils/sidebarPreference.js` exporting `readStoredSidebarCollapsed()` and `writeStoredSidebarCollapsed(isCollapsed)`, mirroring `utils/sessionIdentity.js`'s structure.
- [ ] 1.2 Use `localStorage` (not `sessionStorage`), with a namespaced key (e.g. `siem_sidebar_collapsed`).
- [ ] 1.3 Guard both functions against `typeof window === "undefined"` and wrap all storage access in `try/catch`; never throw.
- [ ] 1.4 `readStoredSidebarCollapsed()` returns `null` unless the stored value parses to a strict boolean — no coercion of arbitrary truthy/falsy values.
- [ ] 1.5 Add `frontend/src/utils/sidebarPreference.test.js` covering: round-trip read/write, missing stored value, corrupt/non-boolean stored value, and storage access throwing (mocked).

## 2. SidebarLayout Persistence

- [ ] 2.1 Initialize `isCollapsed` in `frontend/src/components/SidebarLayout.js` via a lazy `useState` initializer: `readStoredSidebarCollapsed() ?? false`.
- [ ] 2.2 Add a `useEffect` keyed on `[isCollapsed]` that calls `writeStoredSidebarCollapsed(isCollapsed)` on every change.
- [ ] 2.3 Do not add any new prop to `SidebarLayout`'s public contract for this — persistence is internal-only.
- [ ] 2.4 Add/extend `SidebarLayout.test.js` covering: mounting with a previously-stored `true` value starts collapsed; mounting with no stored value or a corrupted value starts expanded; toggling persists the new value (verify via the utility, mocked or via actual storage in a test environment).

## 3. Sidebar Footer Polish

- [ ] 3.1 Add a `title` attribute to the footer's status text element in `frontend/src/components/Sidebar.js`, equal to its own content.
- [ ] 3.2 Add a `title` attribute to the footer's version text element, equal to its own content.
- [ ] 3.3 Confirm missing `statusLabel`/`versionLabel` continue to render no broken/empty row (existing conditional rendering, verified not broken).
- [ ] 3.4 Add/extend `Sidebar.test.js` covering the `title` attributes and the missing-value fallback.
- [ ] 3.5 Do not change any other styling, layout, or prop on `Sidebar`.

## 4. Tests and Build

- [ ] 4.1 Run the full frontend test suite (`npm test -- --watchAll=false`) and confirm all existing tests pass unmodified plus the new/extended tests above.
- [ ] 4.2 Run `npm run build` and confirm it compiles without introducing new warnings beyond the project's existing baseline.
- [ ] 4.3 Confirm `App.js` was not modified and did not need to be.
- [ ] 4.4 Confirm `package.json`/lockfile are unchanged and no new npm dependency was added.

## 5. Manual Verification

- [ ] 5.1 Collapse the sidebar, reload the page, confirm it remains collapsed.
- [ ] 5.2 Expand the sidebar, reload the page, confirm it remains expanded.
- [ ] 5.3 Simulate unavailable or corrupt storage (e.g., via dev tools) and confirm the sidebar still renders, defaulting to expanded, without error.
- [ ] 5.4 Confirm the footer status/version text still renders and shows a tooltip on hover when truncated.
- [ ] 5.5 Confirm existing navigation (section clicks, role-based visibility, programmatic navigation) still works exactly as before.
- [ ] 5.6 Confirm no routing/URL behavior was introduced.
- [ ] 5.7 Confirm no panel behavior changed.

## 6. Final Validation

- [ ] 6.1 Run `openspec validate sidebar-polish-and-persistence --strict` and record the result.
- [ ] 6.2 Run `git diff --check`.
