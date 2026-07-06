## Why

`extract-section-nav-config` centralized section navigation metadata and role-gating into `sectionsConfig`/`isSectionVisible`, but the visible navigation UI in `App.js` is still the original flat pill-button bar. Building a professional collapsible sidebar shell requires new presentational components, and building them directly inside `App.js` would mix "does the new shell render correctly in isolation" with "does wiring it into the live app break anything" in a single risky diff.

This change builds the new shell components — `SidebarLayout`, `Sidebar`, `TopBar` — as standalone, isolated components that consume `sectionsConfig`-shaped data and existing role flags, without touching `App.js` or any panel. Nothing about the running application changes as a result of this spec; the components exist but are not yet reachable by any user.

## What Changes

- Add `frontend/src/components/Sidebar.js`: renders grouped, collapsible navigation from a `sections` array (shaped like `sectionsConfig` entries) and `roleFlags`, highlights the active section, and renders a bottom status/version panel.
- Add `frontend/src/components/TopBar.js`: renders a hamburger toggle button and title/branding area, with a slot for caller-supplied right-aligned content.
- Add `frontend/src/components/SidebarLayout.js`: composes `TopBar` + `Sidebar` + a main content region, owns the collapsed/expanded state, and forwards navigation/role data to `Sidebar`.
- Add matching `*.test.js` files for all three components, tested in isolation with mock data.
- Do not modify `App.js`, any existing panel component, or any service. Do not introduce `react-router-dom`.

## Capabilities

### New Capabilities
- `sidebar-shell-components`: a set of presentational, isolated navigation-shell components (`SidebarLayout`, `Sidebar`, `TopBar`) that render grouped, collapsible, accessible navigation from existing `sectionsConfig`-shaped data, without being wired into the running application.

### Modified Capabilities
- None. `section-nav-config` (from the prior spec) is consumed as-is, unmodified.

## Impact

- Frontend only: three new component files and their tests under `frontend/src/components/`.
- No changes to `App.js`, panel components, services, backend, schema, or routing.
- No new npm dependencies (no icon library, no `react-router-dom`).
- This spec is a direct prerequisite for a later `wire-sidebar-into-app-shell` spec, which will be the only place these components become reachable by real users.
