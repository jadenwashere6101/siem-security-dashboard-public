## Problem Statement

`App.js` currently renders its own inline header and navigation directly (verified against the live file):

- Lines ~431-465: an outer `pageStyle`/`containerStyle` wrapper, a `<header>` containing the "SIEM" eyebrow + "SIEM Dashboard" `<h1>`, an identity block (`Signed in as {currentUsername}` + role badge), a logout button, and a conditional session-change notice.
- Lines ~466-482: a `sectionNavStyle` div rendering one pill `<button>` per `sectionsConfig` entry, gated by `visibleWhen(roleFlags)`, calling `setActiveSection(id)` on click.
- Lines ~484-671: the unchanged content-switch block, each panel gated by both `activeSection === id` and `isSectionVisible(id, roleFlags)`.

`SidebarLayout`, `Sidebar`, and `TopBar` already exist (`build-sidebar-shell-components`), fully tested in isolation, but are imported nowhere. The problem this spec solves is narrow: make the already-built shell the thing `App.js` actually renders, without touching anything downstream of the nav (panels, polling, auth, role logic).

**A real gap found while re-reading the built components:** `SidebarLayout`'s current prop contract (`sections`, `roleFlags`, `activeSectionId`, `onNavigate`, `title`, `statusLabel`, `versionLabel`, `children`) has no way to place content into `TopBar`'s right-side slot — `SidebarLayout` renders `<TopBar isCollapsed={...} onToggleCollapse={...} title={title} />` with no children passed to it at all. The existing identity/logout controls have nowhere to go unless this is fixed. This is addressed directly below (Integration Strategy, Decision 1) rather than worked around.

## Architecture

No new architectural concept is introduced. `App.js` continues to own all state (`activeSection`, `roleFlags`, alerts, auth). The only structural change is what `App.js` renders for its authenticated view:

```
Before:                              After:
<div pageStyle>                      <SidebarLayout
  <div containerStyle>                 sections={sectionsConfig}
    <header> ... </header>              roleFlags={roleFlags}
    <div nav pills> ... </div>          activeSectionId={activeSection}
    {content-switch blocks}             onNavigate={setActiveSection}
  </div>                                title="SIEM Dashboard"
</div>                                  eyebrow="SIEM"
                                         topBarActions={<identity/logout JSX>}
                                         statusLabel={...}
                                         versionLabel={...}
                                       >
                                         {sessionNotice}
                                         {content-switch blocks}
                                       </SidebarLayout>
```

The content-switch block itself (every panel and its `isSectionVisible` gating) moves verbatim into `SidebarLayout`'s `children` — no line inside it changes.

## Integration Strategy

### Decision 1: Add one optional prop, `topBarActions`, to `SidebarLayout` — approved

`SidebarLayout` gains a new optional prop `topBarActions` (a React node), rendered as `<TopBar ...>{topBarActions}</TopBar>`. This is **approved** as the minimal necessary addition to pass the existing identity/logout content into `TopBar`, and it must stay exactly that — the smallest change that unblocks this integration, not a broader `TopBar`/`SidebarLayout` prop redesign.

Rationale: without this, there is no way to integrate identity/logout controls through `SidebarLayout` at all — the alternative would be for `App.js` to bypass `SidebarLayout` and render `TopBar`/`Sidebar` separately itself, which would duplicate the composition/collapse-state logic `SidebarLayout` already owns and contradicts "use the existing architecture whenever possible." Adding one additive, optional prop is smaller and strictly backward compatible: existing `SidebarLayout` usages and tests that don't pass it are unaffected.

Alternatives considered: rendering identity/logout inside `App.js`'s own JSX above or below `<SidebarLayout>`. Rejected — that would produce two separate top bars (the real `TopBar` plus a leftover ad hoc header), which is not "replacing the existing inline navigation shell," just partially replacing it.

### Decision 2: `sessionNotice` moves into `children`, not a new prop

The session-change notice banner (`sessionNoticeStyle` div, shown conditionally when `sessionNotice` is set) is not shell chrome — it's transient page content. It renders as the first child inside `SidebarLayout`'s `children`, above the content-switch block, with its exact existing conditional logic and styling unchanged. No new `SidebarLayout` prop is needed for it.

### Decision 3: `statusLabel`/`versionLabel` use only existing, static data — no new feature

Per the prior spec, `Sidebar`'s bottom panel is "placeholder-friendly" and must not assume real build/version values. This spec passes `versionLabel` from the frontend's existing `package.json` `version` field (already-available static data, no new dependency, no backend call) and a static `statusLabel` (e.g., `"Operational"`). This is intentionally a label, not a live health indicator — building real system-health/version reporting is a new feature and explicitly out of scope.

### Decision 4: Remove obsolete style constants, do not touch anything else

Only the style constants that exclusively supported the removed header/nav JSX are deleted (`sectionNavStyle`, `sectionTabStyle`, `activeSectionTabStyle`, `inactiveSectionTabStyle`, `headerStyle`, App.js's own `topBarStyle`, `sessionActionsStyle`, `pageStyle`, `containerStyle`, `eyebrowStyle`, `titleStyle`). Constants still used by panels or the login/loading screens (`sessionNoticeStyle`, `identityBlockStyle`, `identityLabelStyle`, `roleBadgeStyle` and its role variants, `logoutButtonStyle`, and every panel-facing style like `cardStyle`) are untouched. This is a deletion of now-dead code, not a refactor of live code.

### Decision 5: Preserve the "SIEM" eyebrow via a minimal, additive `TopBar` prop — do not silently drop it

The old header rendered a small uppercase "SIEM" eyebrow label above the "SIEM Dashboard" `<h1>`. Dropping it was reconsidered as an avoidable visible removal — this spec must not remove something a user can see when a small, additive fix preserves it. The approved approach: add one new optional `eyebrow` prop to `TopBar` (a short string, rendered as a small label above `title`, mirroring the old visual exactly), and forward it through `SidebarLayout` via a matching new optional `eyebrow` prop (the same pattern already used for `title`). This is deliberately the same size and shape of change as the `topBarActions` addition — one optional prop, one small render line — not a `TopBar` redesign.

**Explicit scope ceiling:** if implementation finds that preserving the eyebrow requires anything beyond this minimal prop-and-render-line addition (e.g., restructuring `TopBar`'s layout, changing its title contract beyond adding one sibling element, or touching `Sidebar`), implementation MUST stop and report back rather than expanding scope to force it through. In that case, falling back to dropping the eyebrow (the original plan) is an acceptable outcome to report, not a failure — the instruction is "don't silently drop it if a small fix preserves it," not "preserve it at any structural cost."

Alternatives considered: folding "SIEM" into a single combined title string (e.g., `"SIEM — SIEM Dashboard"`) to avoid touching `TopBar` at all. Rejected as the primary approach because it changes the visual treatment (one line instead of two) rather than preserving it, but this remains an acceptable fallback if the `eyebrow` prop addition turns out to need more than described above.

## State Ownership

- **`activeSection`**: unchanged. Remains a plain `useState` in `App.js`. `SidebarLayout`/`Sidebar` receive it as `activeSectionId` and call `onNavigate` (`setActiveSection`) on click — they never set it themselves, per their existing (unmodified) contract.
- **Collapse state (`isCollapsed`)**: unchanged. Remains fully owned inside `SidebarLayout`, exactly as built in the prior spec. `App.js` does not gain new state for this and does not need to.
- **Role flags**: unchanged. `roleFlags = { isSuperAdmin, isAnalyst, canTakeAlertActions }` continues to be computed in `App.js` via the existing `useMemo` and is passed to `SidebarLayout` (which forwards it to `Sidebar`) exactly as it already is to the content-switch block.
- **Authentication state**: unchanged. `isAuthenticated`, `currentUsername`, `userRole`, `authLoading`, and the login-form state remain exactly as they are; the pre-authenticated early-return screens (`authLoading` and `!isAuthenticated`) are untouched, since `SidebarLayout` only wraps the authenticated view.

## Data Flow

1. `App.js` imports `SidebarLayout` (new) alongside its existing `sectionsConfig`/`isSectionVisible` imports.
2. `App.js` renders `<SidebarLayout sections={sectionsConfig} roleFlags={roleFlags} activeSectionId={activeSection} onNavigate={setActiveSection} title="SIEM Dashboard" eyebrow="SIEM" topBarActions={<identity/logout JSX>} statusLabel="Operational" versionLabel={packageVersion}>`.
3. `SidebarLayout` forwards `sections`/`roleFlags`/`activeSectionId`/`onNavigate` to `Sidebar` (unchanged behavior from the prior spec), and `topBarActions`/`eyebrow` to `TopBar` as its `children`/`eyebrow` (new).
4. `Sidebar` filters/groups/renders nav items exactly as already built and tested; clicking one calls `onNavigate(id)`, i.e. `setActiveSection(id)` — the same state setter already used everywhere else in `App.js` (`handleViewRelatedAlerts`, `SocCommandCenter`'s `onNavigate` prop, `handleLogout`).
5. Because every navigation path — sidebar click, `ThreatHuntPanel`'s `onViewRelatedAlerts` → `handleViewRelatedAlerts` → `setActiveSection("dashboard")`, and `SocCommandCenter`'s `onNavigate={setActiveSection}` — all converge on the same `setActiveSection` call, active-item highlighting in `Sidebar` (`activeSectionId === section.id`) stays correct automatically; no new synchronization code is needed.
6. `SidebarLayout` renders its `children` (session notice + the unchanged content-switch block) in its main content region, exactly as `isSectionVisible`-gated today.

## Component Responsibilities

- **`App.js`**: unchanged responsibility — owns all state, all data fetching, all role computation, all panel content. Its only new responsibility is composing `<SidebarLayout>` instead of its own inline header/nav.
- **`SidebarLayout`**: unchanged responsibility (composition root, owns collapse state) plus two new, narrow responsibilities — forwarding `topBarActions` and `eyebrow` to `TopBar`.
- **`Sidebar`**: no responsibility changes; used exactly as already built and tested.
- **`TopBar`**: unchanged responsibility plus one new, narrow addition — rendering an optional `eyebrow` label above `title`, subject to the scope ceiling in Decision 5.

## Scope

**In scope:**
- Replacing `App.js`'s inline header/nav JSX with `<SidebarLayout>`.
- Moving identity/logout JSX into `topBarActions`.
- Moving `sessionNotice` rendering into `SidebarLayout`'s `children`, above the content-switch block.
- Adding the one new `topBarActions` prop to `SidebarLayout` (and matching test coverage).
- Adding the one new `eyebrow` prop to `TopBar` (forwarded through `SidebarLayout`) to preserve the "SIEM" micro-label, unless implementation finds this requires more than a minimal prop-and-render-line addition, in which case: stop and report.
- Supplying `statusLabel`/`versionLabel` from existing static data only.
- Removing now-dead style constants in `App.js` that exclusively supported the removed JSX.

**Out of scope:** (see Non-Goals)

## Non-Goals

- `react-router-dom`, URL routes, or deep-linking of any kind.
- Collapse-state persistence across reloads.
- Visual polish, animation, or icon libraries.
- Any new feature (e.g., real system health/version reporting beyond static labels).
- Any backend, schema, or API change.
- Any change to panel component internals, props, or behavior.
- Any new npm dependency.
- Redesigning or opportunistically refactoring parts of `App.js` unrelated to the header/nav replacement (e.g., alert filtering logic, dashboard metrics helpers, auth flow internals).

## Acceptance Criteria

- `App.js` renders `<SidebarLayout>` for the authenticated view; the old inline header and pill-nav JSX no longer exist in `App.js`.
- `activeSection` remains a `useState` in `App.js`; `SidebarLayout`/`Sidebar` never set it directly.
- Every existing content-switch block renders unchanged, with unchanged `isSectionVisible` gating, as `SidebarLayout`'s `children`.
- Identity block and logout button render inside `TopBar`'s slot via the new `topBarActions` prop, with unchanged styling and unchanged `handleLogout` behavior.
- `sessionNotice` still renders/clears exactly as before (5s timeout), now positioned at the top of `SidebarLayout`'s main content region.
- Clicking a sidebar nav item calls `setActiveSection` with the correct id, and the corresponding panel renders (mount/unmount semantics identical to before).
- `ThreatHuntPanel`'s "view related alerts" flow still navigates to `dashboard` and still applies the source-IP search term.
- `SocCommandCenter`'s internal navigation (`onNavigate={setActiveSection}`) still works and the sidebar's active-item highlight updates to match.
- The 5-second alert polling interval still starts on authentication and stops on logout, unaffected by nav rendering.
- Login and logout flows are visually and behaviorally unchanged (both early-return screens are untouched).
- Role-based visibility is identical to today for `viewer`, `analyst`, and `super_admin` (verified against `sectionsConfig`, unchanged from the prior spec).
- No `react-router-dom`, no new npm dependency, `package.json`/lockfile unchanged.
- `SidebarLayout`'s new `topBarActions` prop is additive and optional; existing `SidebarLayout.test.js` tests that don't pass it continue to pass unmodified, with new tests added for the prop itself.
- The "SIEM" eyebrow label is preserved via the new optional `eyebrow` prop on `TopBar` (forwarded through `SidebarLayout`), unless implementation reports that this requires more than a minimal addition — in which case dropping the eyebrow with an explicit report is an acceptable, documented outcome instead.

## Validation Plan

- Run `npm test -- --watchAll=false` (frontend) and confirm the full suite passes, including `App.test.js` **unmodified** — its `getByRole('button', { name: ... })` queries should keep passing since `Sidebar` renders real `<button>` elements with the same accessible names. If implementation discovers a genuine incompatibility, `App.test.js` may be adapted minimally, but that is a contingency, not the expectation.
- Run `npm run build` and confirm it compiles (matching the project's existing lint/warning baseline — no new warnings introduced by this change).
- Run `openspec validate wire-sidebar-into-app-shell --strict`.
- Run `git diff --check`.
- Manual browser verification (see Risks/Task Breakdown) across `viewer`, `analyst`, `super_admin`: correct sections visible, active highlight follows clicks, `ThreatHunt → Dashboard` and `SocCommandCenter` programmatic navigation both update the highlight correctly, sidebar collapse/expand works, `TopBar` shows correct identity/role/logout and logout works, session-change notice still appears/clears, alert polling continues in the background, login/logout flow is unaffected, and no URL/history behavior was introduced.

## Risk Analysis

- **`topBarActions` gap not caught until implementation** — mitigated by identifying and resolving it now, in the spec, rather than discovering it mid-implementation.
- **`App.test.js` incompatibility** — low likelihood (verified the existing queries are role/name-based, which `Sidebar` already satisfies), but if found, must be fixed minimally and reported, not silently patched around.
- **Preserving the "SIEM" eyebrow requires more than a minimal `TopBar` addition** — mitigated by an explicit scope ceiling (Decision 5): if the minimal `eyebrow` prop approach doesn't work cleanly, implementation MUST stop and report rather than redesigning `TopBar` to force it through; falling back to dropping the eyebrow with a report is an acceptable outcome, not a failure.
- **Cross-navigation highlight desync** — mitigated structurally: every navigation path (sidebar click, `handleViewRelatedAlerts`, `SocCommandCenter.onNavigate`) already converges on the same `setActiveSection`, so `Sidebar`'s `activeSectionId` comparison stays correct without new synchronization code — this must be verified manually, not assumed.
- **Accidentally touching unrelated `App.js` logic while relocating JSX** — mitigated by the explicit Non-Goals list and by keeping the diff limited to the header/nav region and its now-dead style constants.
- **Removing a style constant still used elsewhere** — mitigated by checking each constant's usages before deletion (e.g., `sessionNoticeStyle` must NOT be deleted, since it is still used; only constants with zero remaining references after the JSX move should be removed).

## Migration Plan

1. Add the `topBarActions` prop to `SidebarLayout.js` and its test.
2. Add the `eyebrow` prop to `TopBar.js` (and forward it through `SidebarLayout.js`), with matching test coverage — or, if this proves to require more than a minimal addition, stop and report instead of proceeding.
3. Replace `App.js`'s header/nav JSX with `<SidebarLayout>`, wiring props per the Data Flow section.
4. Move `sessionNotice` rendering and the content-switch block into `SidebarLayout`'s `children`.
5. Remove now-dead style constants from `App.js`.
6. Run the full frontend test suite, the build, and `openspec validate --strict`.
7. Manually verify in a browser per the Validation Plan.
8. Rollback is reverting `App.js`, `SidebarLayout.js`/`SidebarLayout.test.js`, and `TopBar.js`/`TopBar.test.js` to their pre-change state — no backend, schema, or other file is touched.
