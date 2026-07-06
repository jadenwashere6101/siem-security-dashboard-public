## 1. Component Contracts

- [ ] 1.1 Define the `Sidebar` prop contract: `sections` (array shaped like `sectionsConfig` entries: `{ id, label, group, visibleWhen }`), `roleFlags`, `activeSectionId`, `onNavigate(id)`, `isCollapsed`, plus simple status/version footer props.
- [ ] 1.2 Define the `TopBar` prop contract: `isCollapsed`, `onToggleCollapse`, `title`, and a `children` slot for caller-supplied right-aligned content.
- [ ] 1.3 Define the `SidebarLayout` prop contract: `sections`, `roleFlags`, `activeSectionId`, `onNavigate`, `title`, status/version footer props, and `children` (main content).
- [ ] 1.4 Confirm none of the three contracts require importing `sectionsConfig`, `App.js`, or any panel component directly.

## 2. Sidebar Component

- [ ] 2.1 Create `frontend/src/components/Sidebar.js`.
- [ ] 2.2 Filter `sections` to the visible subset by calling each entry's own `visibleWhen(roleFlags)` — do not reimplement or duplicate gating logic.
- [ ] 2.3 Group visible entries by `group` generically (no hardcoded group names) and render a heading/label per group.
- [ ] 2.4 Render one nav `<button>` per visible section with its `label`; mark the entry matching `activeSectionId` with a visual highlight and `aria-current="page"`.
- [ ] 2.5 Call `onNavigate(id)` on click; do not manage or infer active-section state internally.
- [ ] 2.6 Implement collapsed vs. expanded rendering; when collapsed, keep each item's accessible name available even if the visible label text is hidden/truncated.
- [ ] 2.7 Render a bottom status/version panel from simple props (no assumptions about real build/version values — placeholder-friendly props).
- [ ] 2.8 Use a semantic `<nav>` element with an `aria-label`.

## 3. TopBar Component

- [ ] 3.1 Create `frontend/src/components/TopBar.js`.
- [ ] 3.2 Render a hamburger toggle `<button>` that calls `onToggleCollapse`, with `aria-expanded` reflecting `isCollapsed` and `aria-controls` referencing the sidebar nav's id.
- [ ] 3.3 Render the `title`/branding label.
- [ ] 3.4 Render a `children` slot for caller-supplied right-aligned content, with no assumptions about what that content is.
- [ ] 3.5 Do not introduce an icon library dependency; use plain markup/CSS for the hamburger glyph.
- [ ] 3.6 Note for the later `App.js` wiring spec: this spec's tests only verify the slot renders mock content — the wiring spec must explicitly validate that the real identity/logout controls still render and function correctly once placed in this slot.

## 4. SidebarLayout Component

- [ ] 4.1 Create `frontend/src/components/SidebarLayout.js`.
- [ ] 4.2 Own `isCollapsed` via local `useState(false)` and the corresponding toggle handler.
- [ ] 4.3 Render `TopBar`, forwarding `isCollapsed`/toggle handler and `title`.
- [ ] 4.4 Render `Sidebar`, forwarding `sections`, `roleFlags`, `activeSectionId`, `onNavigate`, `isCollapsed`, and status/version footer props.
- [ ] 4.5 Render a plain styled main-content region wrapping `children` — do not create a separate `MainContent` component file.
- [ ] 4.6 Do not read or write `activeSection` state; only forward the props received.

## 5. Tests

- [ ] 5.1 Add `Sidebar.test.js` covering: full visibility, partial visibility for a given `roleFlags`, grouping by `group`, active-item highlight/`aria-current`, collapsed-state accessible name retention, `onNavigate` firing with the correct id, and bottom status/version panel rendering.
- [ ] 5.2 Add `TopBar.test.js` covering: hamburger toggle calling `onToggleCollapse`, `aria-expanded`/`aria-controls` correctness, title rendering, and `children` slot rendering.
- [ ] 5.3 Add `SidebarLayout.test.js` covering: composition of `TopBar` + `Sidebar` + content region, collapse state toggling and propagation to both children, and prop forwarding correctness (`sections`, `roleFlags`, `activeSectionId`, `onNavigate`).
- [ ] 5.4 Confirm no test imports or depends on `App.js`, the real `sectionsConfig.js` content, or any panel component.

## 6. Verification

- [ ] 6.1 Run the full existing frontend test suite and confirm it passes unchanged (regression check that nothing outside the three new files was touched).
- [ ] 6.2 Confirm `git diff`/`git status` shows only new files under `frontend/src/components/` (and their tests) — no modification to `App.js`, panels, services, or `package.json`.
- [ ] 6.3 Confirm no new npm dependency was introduced.
- [ ] 6.4 Run `openspec validate build-sidebar-shell-components --strict` and record the result.
