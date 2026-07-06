## Why

`wire-sidebar-into-app-shell` made the collapsible sidebar the application's live navigation. Two deliberate deferrals remain from the earlier specs, both explicitly flagged as future work at the time: `build-sidebar-shell-components`'s Decision 2 said collapse state is local-only, "not lifted or persisted... if a later spec needs to persist collapse state, that can be added by changing `SidebarLayout`'s internal initializer without changing its external props contract"; and the sidebar's bottom status/version panel was called "placeholder-friendly," using static values (`statusLabel="Operational"`, `versionLabel` from `package.json`) supplied by `App.js` in the wiring spec.

This spec closes both deferrals with the smallest possible changes: persist the collapse preference across reloads via a small `localStorage`-backed utility mirroring the existing `sessionIdentity.js` pattern, and finalize the current static footer/status/version implementation and its polish. Future enhancements to that footer (such as backend health indicators or richer build/version information) remain out of scope for this spec — this spec does not implement them, but it also does not preclude them later. Nothing about routing, panels, or the shell's architecture changes.

## What Changes

- Add `frontend/src/utils/sidebarPreference.js`: a small, try/catch-guarded `localStorage` read/write pair for the sidebar's collapsed/expanded preference, mirroring `utils/sessionIdentity.js`'s existing pattern (safe on missing `window`, safe on storage errors, safe on corrupt/invalid stored data).
- Update `frontend/src/components/SidebarLayout.js`: initialize `isCollapsed` from the stored preference (defaulting to expanded/`false` when no valid preference exists) via a lazy `useState` initializer, and persist `isCollapsed` to storage whenever it changes via a small `useEffect`. No change to `SidebarLayout`'s external props contract.
- Update `frontend/src/components/Sidebar.js`: add native `title` attributes to the footer's status/version text (so truncated/collapsed text remains inspectable via a normal browser tooltip) and a defensive fallback if `versionLabel`/`statusLabel` are missing — no new dependency, no new visual language.
- Add/extend matching test files for all three.
- Do not modify `App.js`, any panel, any service, or the backend.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `sidebar-shell-components`: `SidebarLayout` gains persisted collapse state (internal behavior only, no prop-contract change); `Sidebar`'s footer gains minor, low-risk accessibility/visual polish.

## Impact

- Frontend only: `frontend/src/utils/sidebarPreference.js` (+ test), `frontend/src/components/SidebarLayout.js` (+ test), `frontend/src/components/Sidebar.js` (+ test).
- No changes to `App.js`, any panel, any service, the backend, schema, or routing.
- No new npm dependencies.
- This is the final spec in the sidebar redesign sequence.
