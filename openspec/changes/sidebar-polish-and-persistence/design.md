## Problem Statement

Two things were deliberately deferred by earlier specs in this sequence, not overlooked:

1. **Collapse state does not survive a reload.** `SidebarLayout` (verified against the live file) owns `isCollapsed` via a plain `useState(false)` with no persistence. `build-sidebar-shell-components`'s design explicitly deferred this: *"if a later spec needs to persist collapse state... that can be added by changing `SidebarLayout`'s internal initializer without changing its external props contract."* This spec is that later spec.
2. **The footer/status/version panel is still a placeholder.** `App.js` currently passes `statusLabel="Operational"` and `versionLabel={`v${packageJson.version}`}` into `SidebarLayout` (confirmed live in `App.js`), and `Sidebar` renders them as plain, possibly-truncated text with no fallback handling. This was explicitly scoped as "placeholder-friendly" in the shell-components spec, not as a finished design.

Both are low-risk, narrow, additive changes to already-built, already-tested components. Neither requires touching `App.js`, since `App.js` already supplies everything `SidebarLayout`/`Sidebar` need — this spec is entirely internal to the sidebar shell components.

## Architecture

No new component and no architectural change. `SidebarLayout` keeps owning collapse state exactly as before — the only change is *what initializes and reacts to* that state internally:

```
SidebarLayout (unchanged responsibility, unchanged props contract)
  useState(isCollapsed) initial value: readStoredSidebarCollapsed() ?? false   [changed]
  useEffect: writeStoredSidebarCollapsed(isCollapsed) on change                [new]
  ...renders TopBar + Sidebar + main content exactly as before...

Sidebar (unchanged responsibility, unchanged props contract)
  footer status/version text gains a native `title` attribute + safe fallback  [changed]
```

A new, small, dependency-free utility module supplies the two persistence functions, following the exact shape of the existing `utils/sessionIdentity.js`.

## Persistence Strategy

- **New file `frontend/src/utils/sidebarPreference.js`**, exporting `readStoredSidebarCollapsed()` and `writeStoredSidebarCollapsed(isCollapsed)`, structured identically to `sessionIdentity.js`: guard on `typeof window === "undefined"`, wrap all storage access in `try/catch`, and never throw.
- **Storage mechanism: `localStorage`, not `sessionStorage`.** `sessionIdentity.js` intentionally uses `sessionStorage` because identity is session-scoped auth state that should not outlive the browser tab. Collapse state is a durable UI preference a user reasonably expects to persist across new tabs and browser restarts, so `localStorage` is the correct, deliberately different choice here — not an inconsistency with the existing pattern, but the same pattern applied to a different kind of data.
- **Storage key**: a single namespaced string constant (e.g. `"siem_sidebar_collapsed"`), matching the `"siem_last_identity"` naming convention.
- **Stored value**: a plain boolean, serialized with `JSON.stringify`/parsed with `JSON.parse`, exactly like `sessionIdentity.js` serializes its object.
- **Corrupt or invalid data handling**: if the stored value is missing, fails to parse, or does not parse to a strict boolean, `readStoredSidebarCollapsed()` returns `null` (meaning "no valid preference") rather than throwing or guessing — the caller then falls back to the existing default (`false`, expanded). This mirrors `readStoredSessionIdentity()`'s existing `catch { return null }` behavior exactly.
- **Storage unavailable** (private browsing, disabled storage, quota errors): both functions catch and swallow the error, exactly like `sessionIdentity.js`'s `writeStoredSessionIdentity` already does — the sidebar simply behaves as if no preference exists yet (defaults to expanded) rather than crashing.
- **`SidebarLayout` integration**: `useState(() => readStoredSidebarCollapsed() ?? false)` as the lazy initializer (read once, on mount, not on every render), and a `useEffect(() => { writeStoredSidebarCollapsed(isCollapsed); }, [isCollapsed])` to persist on every change. No new prop is added to `SidebarLayout`'s contract — this is entirely internal behavior, exactly as the prior spec anticipated.

## Footer/Status/Version Strategy

- This spec finalizes the current static values (`statusLabel="Operational"`, `versionLabel` from `package.json`) supplied by `App.js` and their polish, as described below. Future enhancements to this footer — such as backend health indicators or richer build/version information — remain out of scope for this spec; this spec does not implement them, but it also does not prevent them from being proposed and built later. This spec does not add any backend call, polling, or health-check logic; that remains explicitly out of scope (see Non-Goals).
- `Sidebar`'s rendering of `statusLabel`/`versionLabel` gains two small, defensive refinements:
  1. A native HTML `title` attribute on each label's element, set to its own full text, so a user can see the untruncated value via the browser's built-in tooltip if the sidebar's width or `overflow: hidden`/`textOverflow: ellipsis` styling clips it (this styling already exists in `Sidebar.js`; only the `title` attribute is new).
  2. `Sidebar` already renders these conditionally (`{statusLabel && ...}`, `{versionLabel && ...}`); no behavior change is needed there, only confirmation via tests that missing values render no footer row rather than an empty/broken one.
- No new data source, no new prop, no new component. `App.js` continues to supply the same two static strings it already does.

## Accessibility/Polish Boundaries

Eligible (low-risk, additive, no new dependency):
- Native `title` attributes for truncated footer text (above).
- Minor CSS-only refinements using patterns already present in the codebase (e.g., the sidebar's existing `transition: "width 120ms ease"` is a precedent for adding a similarly small, existing-style transition elsewhere, such as a subtle icon rotation on the hamburger button, entirely via inline style — optional, not required).
- Verifying (not changing) that collapse/expand remains keyboard-operable and that `aria-expanded`/`aria-current` semantics from the prior specs still hold after these changes.

Not eligible (explicitly out of scope, see Non-Goals):
- Any new npm dependency (icon libraries, animation libraries, CSS-in-JS tooling).
- Any color/theme redesign, new visual language, or layout restructuring.
- Any change to `Sidebar`/`TopBar`/`SidebarLayout`'s public props contract beyond what Persistence Strategy and Footer Strategy above already specify.
- Any accessibility change that isn't a strict improvement verified by a test — no speculative ARIA additions "just in case."

## Scope

**In scope:**
- `sidebarPreference.js` utility and its tests.
- `SidebarLayout`'s internal collapse-state persistence (lazy init + effect).
- `Sidebar`'s footer `title`-attribute and missing-value-fallback polish.
- Tests for all of the above, including corrupt/unavailable-storage behavior.

**Out of scope:** see Non-Goals.

## Non-Goals

- `react-router-dom`, URL routes, or deep-linking.
- New sections or navigation entries.
- Backend health-check APIs or any real-time status polling.
- Any panel rewrite or panel prop/behavior change.
- Any new npm dependency.
- Any major redesign of the sidebar shell's visual language or component structure.
- Animations beyond what's already achievable with existing CSS/inline style patterns already present in the codebase.
- Any unrelated cleanup in `App.js` or elsewhere — this spec touches only the three files listed in Impact.
- Changing `SidebarLayout`'s or `Sidebar`'s external props contract (the persistence and footer changes are internal-behavior-only).

## Acceptance Criteria

- `sidebarPreference.js` exports `readStoredSidebarCollapsed()`/`writeStoredSidebarCollapsed()`, both safe against missing `window`, storage errors, and corrupt/invalid stored values (never throw; `read` returns `null` on any failure).
- `SidebarLayout` initializes `isCollapsed` from `readStoredSidebarCollapsed() ?? false` on mount, and persists every subsequent change via `writeStoredSidebarCollapsed`.
- Reloading (re-mounting `SidebarLayout` in a test, simulating a reload) with a previously-stored `true` value results in the sidebar starting collapsed; with no stored value or a corrupted stored value, it starts expanded (`false`), matching today's default.
- `SidebarLayout`'s public props contract is unchanged — no new prop was added for persistence.
- `Sidebar`'s footer status/version text carries a `title` attribute equal to its own content; missing `statusLabel`/`versionLabel` render no broken/empty row.
- No new npm dependency; `package.json`/lockfile unchanged.
- `App.js` is untouched; `git diff` for this change touches only the three files (plus tests) listed in Impact.
- All pre-existing `SidebarLayout.test.js`/`Sidebar.test.js` assertions continue to pass unmodified.

## Validation Plan

- Run `npm test -- --watchAll=false` (frontend) and confirm the full suite passes, including new tests for: stored-preference read on mount, persistence on toggle, safe fallback when storage is unavailable (mocked to throw) or contains corrupt/non-boolean data, and footer `title`-attribute/fallback behavior.
- Run `npm run build` and confirm it compiles without introducing new warnings beyond the project's existing baseline.
- Run `openspec validate sidebar-polish-and-persistence --strict`.
- Run `git diff --check`.
- Manual browser verification: collapse the sidebar, reload the page, confirm it stays collapsed; expand it, reload, confirm it stays expanded; simulate unavailable/corrupt storage (e.g., via dev tools) and confirm the sidebar still renders expanded without error; confirm the footer status/version text still renders (and shows a tooltip on hover if truncated); confirm existing navigation (clicking sections, role visibility, programmatic navigation) still works exactly as before; confirm no routing/URL change was introduced; confirm no panel behavior changed.

## Risk Analysis

- **Storage read/write failure crashing the app** — mitigated by mirroring `sessionIdentity.js`'s proven try/catch-everywhere pattern exactly; every failure path returns a safe default instead of throwing.
- **Corrupt stored data producing an invalid collapse state** (e.g., a stray non-boolean value silently coerced to truthy) — mitigated by strict validation in `readStoredSidebarCollapsed()`: only a literal `true`/`false` after successful `JSON.parse` is accepted; anything else returns `null`, and the caller's `?? false` fallback applies.
- **Persisting on every render instead of only on change** — mitigated by using a lazy `useState` initializer (runs once) and a `useEffect` keyed on `[isCollapsed]` (runs only when it actually changes), not a write-on-every-render pattern.
- **Footer polish accidentally changing layout/behavior** — mitigated by scoping the change to a `title` attribute addition and a defensive fallback check only; no existing style property, conditional rendering path, or prop is altered.
- **Scope creep into visual redesign** — mitigated by the explicit Accessibility/Polish Boundaries section listing exactly what's eligible, and Non-Goals ruling out anything broader.
- **`localStorage` vs `sessionStorage` inconsistency confusion** — mitigated by documenting explicitly (Persistence Strategy) why this is a deliberate, different choice from `sessionIdentity.js`, not an oversight.

## Migration Plan

1. Add `sidebarPreference.js` and its tests.
2. Update `SidebarLayout.js` to initialize and persist `isCollapsed` via the new utility; add matching tests.
3. Update `Sidebar.js`'s footer with `title` attributes and fallback handling; add matching tests.
4. Run the full frontend test suite, the build, and `openspec validate --strict`.
5. Manually verify in a browser per the Validation Plan.
6. Rollback is reverting the three changed files and deleting `sidebarPreference.js`/its test — no other file is touched.
