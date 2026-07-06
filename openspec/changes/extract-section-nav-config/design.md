## Context

`frontend/src/App.js` currently owns all navigation and content rendering directly:

- `activeSection` (`useState`, `App.js:47`) is the sole navigation state. There is no `react-router-dom` dependency and `index.js` mounts `<App />` with no router — this is a single-URL SPA and must remain one.
- The nav-button block (`App.js:461-608`) renders one hardcoded `<button>` per section, each wrapped in an inline role check (`canTakeAlertActions`, `isSuperAdmin`, or no check for `dashboard`).
- The content-switch block (`App.js:610-797`) renders one conditional panel per section (`{activeSection === "x" && <Panel/>}`), each wrapped in the *same* role check repeated a second time.
- There are exactly 12 sections today: `dashboard`, `soc-command-center`, `blocklist`, `threat-hunt`, `administration`, `soar-queue`, `soar-incidents`, `soar-approvals`, `soar-playbooks`, `soar-playbook-metrics`, `soar-integrations`, `soar-operations`.
- Every panel component self-fetches its own data on mount via its own `useEffect` and receives no navigation-related props beyond a few style objects and callbacks — panel internals are unrelated to how navigation is rendered and must not be touched here.
- There is no React Context/Provider tree anywhere in the app; all state is prop-drilled from `App.js`. This refactor has nothing else to integrate with.

This is the first of several planned specs toward a collapsible sidebar shell. This spec is scoped narrowly to the config-extraction step only, so the highest-risk, most visible cutover work (wiring an actual sidebar into `App.js`) happens later, against an already-de-duplicated data source.

## Goals / Non-Goals

**Goals:**
- Define one `sectionsConfig` array as the single source of truth for `id`, `label`, `group`, and `visibleWhen(roleFlags)` for all 12 existing sections.
- Refactor both the nav-button block and the content-switch block in `App.js` to read from this same config, removing the duplicated inline conditions.
- Preserve all 12 `activeSection` id strings exactly as they exist today (nothing renamed, added, or removed).
- Produce zero visible UI change: identical button text, order, styling, and click behavior; identical panel rendering and prop passing.
- Keep the existing single-URL SPA behavior fully intact.

**Non-Goals:**
- No sidebar, hamburger, collapsible layout shell, or `SidebarLayout`/`TopBar`/`Sidebar` components (later specs).
- No grouped-navigation *UI* (the `group` field is defined now for later reuse, but no visual grouping is rendered in this spec).
- No `react-router-dom`, URL, or deep-linking changes of any kind.
- No visual/style redesign of the existing pill nav.
- No changes to any panel component's internals, props, or behavior.

## Decisions

### Decision 1: Config shape and location

`sectionsConfig` is added at `frontend/src/utils/sectionsConfig.js`, following the existing convention of `utils/sessionIdentity.js` and `utils/siemPath.js` (small, dependency-free helper modules). Each entry has the shape:

```
{ id: string, label: string, group: string, visibleWhen: (roleFlags) => boolean }
```

`roleFlags` mirrors the flags already computed in `App.js` (`isSuperAdmin`, `isAnalyst`, `canTakeAlertActions`) so `visibleWhen` can be a pure, easily-unit-tested function with no new role concepts introduced.

Alternatives considered: keeping the config inline in `App.js` as a local constant. Rejected because the later sidebar components need to import the same config independently of `App.js`, and a separate module makes that reuse trivial without a circular import.

### Decision 2: `visibleWhen` must be an exact 1:1 port, not a reinterpretation

For each of the 12 sections, `visibleWhen` must reproduce the *exact* current inline condition — not a "cleaned up" or "simplified" version. For example, `dashboard` has no gating (always visible), `administration` and `soar-queue` require `isSuperAdmin`, and the remaining sections require `canTakeAlertActions`.

Rationale: the audit identified drift between duplicated conditions as the main risk. The safest way to remove that risk is to port the existing truth table verbatim into one place, not to redesign the role model at the same time.

### Decision 3: Both consumers must migrate together, in the same change

Refactoring only the nav block (or only the content block) to use `sectionsConfig`, while leaving the other with its original inline condition, would recreate exactly the divergence risk this spec exists to remove. Both must be migrated in this same change.

Alternatives considered: splitting nav-consumption and content-consumption into two separate specs. Rejected — a half-migrated state is strictly worse than the current fully-duplicated-but-consistent state, since it could reintroduce silent drift between the migrated and un-migrated copy.

### Decision 4: Zero visual change is a hard constraint for this spec

This spec must not change what the user sees. The sidebar shell, hamburger, grouping UI, and layout changes are explicitly deferred to later specs (`build-sidebar-shell-components`, `wire-sidebar-into-app-shell`). Keeping this spec visually inert makes `App.test.js` passing unmodified a strong, cheap regression signal.

## Risks / Trade-offs

- **`visibleWhen` mismatch**: if a ported condition doesn't exactly match the original, a role could silently gain or lose access to a section. Mitigated by an explicit parity table (Task 1) reviewed before implementation, and unit tests in `sectionsConfig.test.js` asserting the same visibility outcome as today for every section × representative role combination (super_admin, analyst, viewer, unauthenticated).
- **Existing nav/content conditions already disagree**: if the parity audit (Task 1) finds that the current nav-block condition and content-block condition for some section already disagree with each other today, that is a pre-existing bug this spec did not create and should not silently resolve either way. Implementation must stop and report the mismatch rather than picking one side as authoritative, since the correct resolution may require a decision outside this spec's scope.
- **Missed or extra section id**: mitigated by asserting `sectionsConfig` contains exactly the 12 listed ids, no more and no fewer.
- **Accidental visual drift during refactor**: mitigated by keeping `App.test.js` unmodified as the acceptance gate — any required test change is a signal this spec exceeded its scope.
- **Scope creep into sidebar work**: mitigated by this spec's explicit non-goals; any sidebar/layout work discovered as "easy to also do here" should be deferred to the later specs instead.

## Acceptance Criteria

- `frontend/src/utils/sectionsConfig.js` exports exactly 12 entries, one per existing `activeSection` id, each with `id`, `label`, `group`, and `visibleWhen`.
- `visibleWhen` for every entry reproduces the current inline gating condition exactly (verified against the parity table in Task 1).
- `App.js`'s nav-button block renders by iterating `sectionsConfig` and calling `visibleWhen(roleFlags)`; no duplicated inline visibility conditions remain in the nav block.
- `App.js`'s content-switch block gates on the same `sectionsConfig` entries; no duplicated inline visibility conditions remain in the content block.
- No new components, no CSS/style changes, no change to button text, order, or click behavior.
- `App.test.js` passes without modification.
- `frontend/src/utils/sectionsConfig.test.js` passes and demonstrates role-visibility parity with the original 12-section behavior.

## Validation Plan

- Run the full frontend test suite (`CI=true npx react-scripts test --watchAll=false` from `frontend/`) and confirm all existing tests pass unmodified, plus the new `sectionsConfig.test.js`.
- Manually diff `App.js` before/after to confirm no rendered-output change (same JSX text/order/styles), independent of the internal data-source refactor.
- Manually smoke-test the pill navigation in a browser for each tested role (super_admin, analyst, viewer), confirming it looks and behaves identically to before this change, before any sidebar work begins.
- Run `openspec validate extract-section-nav-config --strict` and confirm it passes.

## Migration Plan

1. Add `frontend/src/utils/sectionsConfig.js` and `frontend/src/utils/sectionsConfig.test.js`.
2. Refactor `App.js`'s nav-button block to iterate `sectionsConfig`.
3. Refactor `App.js`'s content-switch block to gate on the same `sectionsConfig` entries.
4. Run the full frontend test suite.
5. Rollback is reverting the `App.js` diff and deleting `sectionsConfig.js`/its test — no backend, schema, or route impact to unwind.
