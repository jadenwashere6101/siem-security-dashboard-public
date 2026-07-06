## Why

`extract-section-nav-config` centralized navigation metadata into `sectionsConfig`, and `build-sidebar-shell-components` built `SidebarLayout`, `Sidebar`, and `TopBar` as isolated, tested components consuming that same data. Neither change touched the running application — `App.js` still renders its original inline pill-button header and nav. The sidebar shell exists but nobody can see it.

This change performs the one remaining step: replacing `App.js`'s inline header/nav JSX with `SidebarLayout`, so the already-built, already-tested shell becomes the application's real navigation. Every other behavior in `App.js` — `activeSection` ownership, role gating, panel rendering, polling, authentication — is preserved exactly as it exists today; only the chrome around it changes.

## What Changes

- Replace `App.js`'s inline header (title, identity block, logout button, session notice) and inline pill-button nav block with `<SidebarLayout>`, passing `sectionsConfig` as `sections`, the existing `roleFlags`, `activeSection`/`setActiveSection` as `activeSectionId`/`onNavigate`, and the existing identity/logout JSX as `topBarActions`.
- Add one new, additive, optional prop to `SidebarLayout` — `topBarActions` (approved) — forwarded as `TopBar`'s `children`. This is the one necessary extension to the already-built shell: its current contract has no way to place caller content in `TopBar`'s right-side slot, which is required to preserve the existing identity/logout controls.
- Add one new, additive, optional prop to `TopBar` — `eyebrow` — forwarded through `SidebarLayout`, to preserve the existing "SIEM" micro-label above the title rather than silently dropping it. If implementation finds this requires more than a minimal prop-and-render-line addition, implementation must stop and report instead of expanding scope; falling back to dropping the eyebrow is an acceptable, documented outcome in that case.
- Remove the now-obsolete inline nav/header JSX and its now-unused style constants from `App.js` (`sectionNavStyle`, `sectionTabStyle`, `activeSectionTabStyle`, `inactiveSectionTabStyle`, `headerStyle`, `topBarStyle` (App.js's own, distinct from the `TopBar` component), `sessionActionsStyle`, `pageStyle`, `containerStyle`, `eyebrowStyle`, `titleStyle`).
- Preserve every other line of `App.js` unchanged: `activeSection` state, `roleFlags`, all panel content-switch blocks (including their `isSectionVisible` gating), polling effect, authentication flow, `handleViewRelatedAlerts`, `SocCommandCenter`'s `onNavigate` prop.
- Do not introduce `react-router-dom`, URL state, collapse persistence, or any new npm dependency.

## Capabilities

### New Capabilities
- None. This change wires already-defined capabilities together; it does not introduce new user-facing capability beyond making the existing sidebar shell reachable.

### Modified Capabilities
- `sidebar-shell-components`: `SidebarLayout` gains one new optional prop (`topBarActions`, approved) to support real integration; `TopBar` gains one new optional prop (`eyebrow`) to preserve the existing "SIEM" micro-label rather than dropping it, subject to an explicit scope ceiling (see design.md Decision 5); `Sidebar` is unchanged.

## Impact

- Frontend only: `frontend/src/App.js` (primary integration target), `frontend/src/components/SidebarLayout.js` (two new optional props: `topBarActions`, `eyebrow`), `frontend/src/components/SidebarLayout.test.js`, `frontend/src/components/TopBar.js` (one new optional prop: `eyebrow`), and `frontend/src/components/TopBar.test.js` — all justified as minimal, additive extensions to the already-built shell.
- No changes to any panel component, any service, the backend, schema, or routing.
- No new npm dependencies.
- `App.test.js` is expected to require no modification — it queries nav items by accessible role/name, which `Sidebar` already preserves.
- This is the final spec in the sidebar redesign sequence; after this change, the collapsible sidebar is the application's live navigation.
