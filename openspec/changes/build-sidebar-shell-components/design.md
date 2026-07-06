## Context

`sectionsConfig` (`frontend/src/utils/sectionsConfig.js`) now exists as the single source of truth for navigation metadata: an array of `{ id, label, group, visibleWhen(roleFlags) }` entries, plus an `isSectionVisible(sectionId, roleFlags)` helper. `App.js` already consumes it for both nav rendering and content gating (`roleFlags = { isSuperAdmin, isAnalyst, canTakeAlertActions }`, computed via `useMemo` in `App.js`). Groups currently present in the data are `overview`, `soc`, `soar`, and `administration`.

The application has no `react-router-dom`, no React Context/Provider tree, and no icon library dependency. `activeSection` remains a plain `useState` owned by `App.js`. This spec must not disturb any of that — it only adds new, disconnected component files.

## Architecture

Three components, each with one clear responsibility, composed top-down:

```
SidebarLayout            (owns collapsed/expanded state; composition root)
 ├── TopBar               (hamburger toggle, title, right-side slot)
 ├── Sidebar               (grouped nav, active highlight, status/version footer)
 └── <main content region>  (renders children — the future page content)
```

No separate `MainContent` file is introduced. "Main content container" is a plain styled wrapper `<div>` inside `SidebarLayout` around `children` — a fourth component would be speculative given it has no behavior of its own (see Decision 4).

## Component Responsibilities

- **`Sidebar`**: pure presentational. Given a `sections` array (entries shaped like `sectionsConfig`: `{ id, label, group, visibleWhen }`) and `roleFlags`, filters to visible sections by calling each entry's own `visibleWhen(roleFlags)`, groups the visible entries by their `group` field (grouping is generic — `Sidebar` does not hardcode group names like `soc` or `soar`), renders one nav button per visible section, marks the section matching `activeSectionId` as active, and renders a bottom status/version panel from simple props. Renders differently (narrower, label text visually hidden but still accessible) when `isCollapsed` is true.
- **`TopBar`**: pure presentational. Renders a hamburger `<button>` that calls `onToggleCollapse`, a `title`/branding label, and a `children` slot for caller-supplied right-aligned content (e.g., identity/logout controls) — `TopBar` does not know or care what that content is. This spec's tests only verify the slot renders arbitrary mock content; the later `App.js` wiring spec must explicitly validate that the real identity/logout controls still render and function correctly once placed in that slot — passing mock content here is not evidence that the real integration works.
- **`SidebarLayout`**: composition root. Owns `isCollapsed` (`useState`, local to this component) and the toggle handler; renders `TopBar` and `Sidebar`, forwarding the collapse state/toggle and navigation props respectively; renders `children` inside the main content region. Does not own `activeSection`, does not know about routing, does not fetch data.

## State Ownership

- **`activeSection`**: NOT owned by any component in this spec. `SidebarLayout`/`Sidebar` accept `activeSectionId` and `onNavigate(id)` as props and call `onNavigate` on click — ownership stays with whatever renders `SidebarLayout` later (currently `App.js`, unchanged by this spec).
- **`isCollapsed`**: owned locally inside `SidebarLayout` via `useState(false)`, not lifted to a prop or context. Nothing outside `SidebarLayout` needs it in this spec, so lifting it now would be speculative. If a later spec needs to persist collapse state (e.g., across reloads), that can be added by changing `SidebarLayout`'s internal initializer without changing its external props contract.
- **Role gating**: NOT computed by any of these components. `Sidebar` receives already-shaped `sections` entries (each with its own `visibleWhen`) and `roleFlags`, and calls the existing `visibleWhen` functions directly — it does not reimplement or duplicate gating logic, and it has no knowledge of what `isSuperAdmin`/`canTakeAlertActions` mean.
- **Section list content**: `Sidebar` does not import `sectionsConfig` directly. It accepts a `sections` prop. This keeps the component testable in isolation with small mock arrays and defers the decision of "pass the real `sectionsConfig` vs. a filtered subset" to the wiring spec.

## Data Flow

1. Caller (later, `App.js`) will import `sectionsConfig` and pass it, along with the existing `roleFlags` and `activeSection`/`setActiveSection`, into `SidebarLayout` as `sections`, `roleFlags`, `activeSectionId`, `onNavigate`.
2. `SidebarLayout` forwards `sections`, `roleFlags`, `activeSectionId`, `onNavigate` to `Sidebar` unchanged, and forwards its own `isCollapsed`/toggle handler to both `Sidebar` and `TopBar`.
3. `Sidebar` filters `sections` to the visible subset (`entry.visibleWhen(roleFlags)`), groups by `entry.group`, and renders. Clicking a nav item calls `onNavigate(entry.id)` — it does not call `setActiveSection` itself, since it doesn't own that state.
4. `SidebarLayout` renders `children` (the future page content) in the main content region, unrelated to navigation state.

This spec does not perform step 1 — that is exactly what `wire-sidebar-into-app-shell` will do. In this spec, tests exercise steps 2-4 directly with mock props.

## Accessibility Requirements

- Every nav item is a real `<button>` (or `<a>`-like element with `role="button"`) with a visible or `aria-label`-provided accessible name — matching the existing convention already verified by `App.test.js`'s `getByRole('button', { name: ... })` queries, so a later wiring spec can keep those tests passing.
- The nav region is a semantic `<nav>` with `aria-label` (e.g., `"Primary"`).
- The active section is marked with `aria-current="page"` in addition to any visual highlight — highlighting must not be conveyed by color alone.
- The hamburger toggle button has `aria-expanded` reflecting `isCollapsed` and `aria-controls` referencing the sidebar nav's id.
- When collapsed, each nav item's accessible name must remain available (e.g., visually truncated/hidden label text kept in the DOM, or an explicit `aria-label`) — collapsing must not remove the accessible name, only its visible text.
- Grouped sections use a heading element or `aria-label` per group so the grouping is conveyed to assistive technology, not just visually.

## Decisions

### Decision 1: Sidebar filters visibility itself, using the same `visibleWhen` functions already in `sectionsConfig`

Rationale: the prior spec's entire purpose was making `visibleWhen` the one place gating logic lives. Having `Sidebar` call `entry.visibleWhen(roleFlags)` directly reuses that same function reference — it is not a new, third copy of gating logic, just a new call site for the one that already exists.

Alternatives considered: requiring the caller to pre-filter `sections` before passing them in. Rejected because it would push filtering responsibility outward and make it possible (in the future wiring spec or beyond) to forget to filter, silently showing a section nobody is allowed to see. Filtering inside `Sidebar` makes it structurally impossible to skip.

### Decision 2: `isCollapsed` is local state inside `SidebarLayout`, not lifted or persisted

Rationale: nothing in this spec, or in the currently-known next spec, needs to read or set collapse state from outside `SidebarLayout`. Lifting it to a prop, context, or storage layer now would be speculative — exactly what the stated implementation philosophy asks to avoid.

Alternatives considered: persisting collapse state to `sessionStorage` immediately (mirroring `utils/sessionIdentity.js`). Rejected for this spec — deferred as an optional future enhancement, not required by any stated goal here.

### Decision 3: No new npm dependencies — no icon library

Rationale: the codebase has no existing icon dependency, and introducing one is a build/dependency-surface decision bigger than "build a sidebar shell." The hamburger toggle and any visual affordances use plain markup/CSS (e.g., a simple three-line glyph via CSS or Unicode character) rather than pulling in a new package.

Alternatives considered: adding a small icon library (e.g., `react-icons`) for a polished hamburger/chevron look. Rejected for this spec; can be revisited explicitly later if the plain-markup approach looks visually insufficient — that is a design/polish decision, not an architecture one, and shouldn't block this spec.

### Decision 4: No separate `MainContent` component file

Rationale: "main content container" has no behavior — it is a styled wrapper around `children`. Giving it its own file/props contract would be an abstraction with nothing to abstract. It lives as a plain region inside `SidebarLayout`.

Alternatives considered: a dedicated `MainContent.js` for symmetry with `Sidebar.js`/`TopBar.js`. Rejected as speculative — if it ever needs real behavior (e.g., its own loading state), it can be extracted then.

### Decision 5: Components are built and tested in isolation; nothing is wired into `App.js`

Rationale: this matches the spec's explicit scope. Testing with mock `sections`/`roleFlags` data (not the real `sectionsConfig` import) keeps these tests independent of the real business config and of `App.js`, so this spec can be fully validated without touching the live app.

## Scope

**In scope:**
- `Sidebar.js`, `TopBar.js`, `SidebarLayout.js` and their tests.
- Grouped navigation rendering, collapsed/expanded states, hamburger toggle, active-section highlighting, bottom status/version panel.
- Accessibility behavior described above.
- Consuming `sectionsConfig`-shaped data via props (not importing the real config directly).

**Out of scope:**
- Any change to `App.js`.
- Replacing the existing pill navigation.
- Changing `activeSection` ownership or the SPA's single-URL behavior.
- Introducing `react-router-dom` or any URL/routing behavior.
- Changing any panel component's rendering, props, or behavior.
- New npm dependencies (icon libraries, animation libraries, state-management libraries).
- Collapse-state persistence across reloads (left as a future, separate enhancement).

## Acceptance Criteria

- `Sidebar.js`, `TopBar.js`, `SidebarLayout.js` exist and export functioning React components matching the responsibilities above.
- `Sidebar` correctly filters a mixed `sections` array (some visible, some not, for a given `roleFlags`) using each entry's own `visibleWhen`.
- `Sidebar` groups rendered items by `group` and renders a heading/label per group.
- `Sidebar` renders a bottom status/version panel from props.
- `Sidebar` and `SidebarLayout` both support a collapsed and an expanded visual state, toggled via `TopBar`'s hamburger button.
- The active section (matching `activeSectionId`) is visually and semantically (`aria-current="page"`) distinguished from inactive sections.
- Clicking a nav item calls the supplied `onNavigate(id)` callback with the correct section id; no internal navigation state is required to observe this.
- All accessibility requirements above are met and covered by tests (accessible names present when collapsed, `aria-expanded`/`aria-controls` on the toggle, `aria-current` on the active item).
- `App.js` is untouched; `git diff` for this change touches only new files under `frontend/src/components/`.
- No new npm dependency is added (`package.json` unchanged).

## Validation Plan

- Add and run component tests for `Sidebar.js`, `TopBar.js`, `SidebarLayout.js` using mock `sections`/`roleFlags` data covering: full visibility, partial visibility (some sections hidden for a role), grouping, collapsed/expanded rendering, active-item highlighting, hamburger toggle behavior, and `onNavigate` callback firing with correct ids.
- Add explicit accessibility assertions: accessible name presence for collapsed items, `aria-expanded`/`aria-controls` on the toggle button, `aria-current="page"` on the active item, semantic `<nav>`/group labeling.
- Run the full existing frontend test suite (`CI=true npx react-scripts test --watchAll=false` from `frontend/`) and confirm it passes unchanged — since no existing file is modified, this is a pure regression check confirming nothing was accidentally touched.
- Confirm `package.json` has no new dependencies (`git diff --check` / `git status` on `package.json` and lockfile shows no changes).
- Run `openspec validate build-sidebar-shell-components --strict` and confirm it passes.

## Risks / Trade-offs

- **Accessibility regressions baked in early**: since these components will become the only nav surface in a later spec, any accessibility gap here (e.g., missing accessible name when collapsed) would ship broadly later. Mitigated by making accessibility requirements explicit acceptance criteria and testing them now, in isolation, before any wiring risk is added.
- **Prop contract mismatch with the eventual wiring spec**: if `SidebarLayout`'s props don't match what `App.js` actually has available (`roleFlags`, `activeSection`, `setActiveSection`, `sectionsConfig`), the next spec would need to adapt either side. Mitigated by explicitly designing the prop shapes in this spec to mirror what already exists in `App.js` today (documented in Data Flow above), rather than inventing an unrelated shape.
- **`TopBar` slot tested only with mock content**: this spec verifies `TopBar`'s `children` slot renders arbitrary mock content, not that the real identity/logout controls work inside it. That gap is deliberate — this spec has no reason to know what real content will go there — but it means slot tests passing here are not sufficient evidence the eventual integration works. Mitigated by requiring the later `App.js` wiring spec to explicitly re-validate that the real identity/logout controls render and function correctly once placed in `TopBar`'s slot.
- **Over-abstracting the shell**: risk of adding a `MainContent` component, a context provider, or persisted collapse state "while we're at it." Mitigated by Decisions 2-4 explicitly rejecting those additions for this spec.
- **Introducing a new dependency for polish (icons)**: risk of quietly adding an icon package to make the hamburger/chevrons look better. Mitigated by Decision 3 — plain markup only; revisit explicitly later if needed.

## Migration Plan

1. Add `Sidebar.js`, `TopBar.js`, `SidebarLayout.js` under `frontend/src/components/`.
2. Add matching test files with mock data covering the acceptance criteria.
3. Run the new tests plus the full existing frontend suite.
4. Run `openspec validate build-sidebar-shell-components --strict`.
5. Rollback is deleting the three new files and their tests — no other file is touched, so there is nothing else to unwind.
