## Context

The frontend is a single React shell. `App.js` owns `activeSection`, dashboard alert filters, selected alert state, and programmatic workspace pivots such as alert, incident, playbook, approval, and Response Registry navigation. `SidebarLayout` already receives `navigationRequest` and owns the real scrollable `<main>` container, while `TopBar` provides the top-left header area where Back/Forward controls should live.

Current navigation is destination-aware but not history-aware. A pivot can move an analyst to the correct workspace or element, but there is no stack of previous investigation contexts and browser Back normally does not restore prior SIEM workspace state.

## Goals / Non-Goals

**Goals:**
- Add an analyst workspace history stack with Back and Forward controls.
- Restore investigation context using small serializable snapshots.
- Integrate browser Back/Forward with the workspace history without adopting a router.
- Keep history bounded, session-local, and safe across login/logout and role changes.
- Preserve current sidebar navigation, programmatic pivots, scroll/focus behavior, RBAC visibility, and data-loading contracts.

**Non-Goals:**
- Do not redesign routing, introduce React Router, change backend APIs, or persist history server-side.
- Do not store API result datasets, full detail payloads, secrets, or large UI state.
- Do not change ingest, detection, alerts, SOAR, AI, exports, or database schema.
- Do not attempt perfect restoration of every incidental UI toggle; restore only analyst investigation context.

## Decisions

1. **Use an app-level workspace history controller in `App.js`.**
   - Rationale: `App.js` already coordinates active workspace, cross-workspace pivots, alert filters, selected alert, and child initial request objects.
   - Alternative considered: per-panel local histories. Rejected because Back/Forward must cross workspaces and preserve shared dashboard filters.

2. **Represent entries as bounded serializable snapshots.**
   - Each entry should include `sectionId`, optional `target`, `label`, `createdAt`, and a `state` object with only supported restoration metadata.
   - Initial target size: keep the latest 50 entries and dedupe equivalent consecutive entries.
   - Store IDs, filter values, sort keys, offsets, tab/view IDs, expanded row IDs, and scroll position. Do not store row arrays, API responses, AI transcript contents, or sensitive payloads.

3. **Centralize capture/restore in new navigation helpers.**
   - Add a utility such as `frontend/src/utils/workspaceHistory.js` for entry normalization, dedupe keys, stack transitions, browser-state markers, and snapshot validation.
   - Keep panel-specific state adapters small and explicit so unsupported panels fall back to workspace-only restoration.

4. **Create history only for meaningful investigation actions.**
   - Capture: sidebar workspace changes, opening an alert, opening related alerts/source context, opening incident/playbook/approval/registry/recon history/detail pivots, and explicit selected master-detail records where supported.
   - Do not capture every keystroke, hover, refresh, auto-load, loading completion, AI panel update, notification refresh, or sidebar collapse.
   - Filter/search/sort/pagination changes should update the current entry metadata and be restored, but should not flood the stack until they are followed by a meaningful navigation action.

5. **Integrate browser history lightly.**
   - On application readiness, write a SIEM-owned `history.state` marker for the current workspace.
   - When pushing a new workspace-history entry, also call `window.history.pushState` with `{ siemWorkspaceHistory: true, entryId }`.
   - On `popstate`, restore the matching workspace-history entry if present. If the event is not SIEM-owned, leave browser behavior alone.
   - Guard against feedback loops with an `isRestoring` flag.

6. **Restore scroll in `SidebarLayout` when practical.**
   - Extend the existing navigation request contract with optional `restoreScrollTop`.
   - Restore scroll after the target workspace renders, then focus the best available heading/detail element.
   - If the saved scroll target cannot be applied, fall back to existing top/element behavior.

7. **Place controls in the top-left header.**
   - Update `TopBar` to accept a `navigationControls` slot rendered after the hamburger and before the title.
   - Add compact Back/Forward buttons using existing dark SIEM button styling and clear disabled states.

## State Restoration Strategy

Restore first-phase state in these areas:
- Dashboard: `activeSection`, `alertView`, `selectedAlertId`, expanded alert row via selected ID, pagination/sort/search/filter state, and Recent Alerts element target.
- SOC Command Center: selected incident, selected recon activity, selected source-IP drawer where exposed through controlled props or an initial request.
- Recon History: filters/search/sort/pagination, selected recon activity, linked-alert pagination.
- Response Registry: view, query, exact indicator, related alert/incident/playbook/approval context, selected entry.
- SOAR Incidents, Approvals, Playbooks, Queue: selected IDs and status/view filters where existing initial request patterns exist.
- Threat Hunt and Live Logs: filters/search/sort/pagination/expanded event only if the panel can expose controlled initial state without broad refactor.
- Scroll: restore `main.scrollTop` for the workspace entry when the target is still valid.

Fallback behavior: if a saved section is no longer visible for the current role, restore Dashboard and clear invalid entity selection.

## Navigation Lifecycle

1. Capture the current workspace snapshot before a meaningful navigation changes state.
2. Push the new destination snapshot to the back stack and clear the forward stack.
3. Apply the destination state through existing setters and initial request props.
4. Create or update a browser history marker for the entry.
5. Back moves current entry to the forward stack, restores the previous entry, and updates browser state.
6. Forward moves the next forward entry back to current, restores it, and updates browser state.
7. Login, logout, failed auth, role downgrade, and explicit default-landing application reset the stacks.

## Expected Files to Change

- `frontend/src/App.js`
- `frontend/src/components/TopBar.js`
- `frontend/src/components/SidebarLayout.js`
- `frontend/src/utils/workspaceNavigation.js`
- New `frontend/src/utils/workspaceHistory.js`
- Existing panel components only where needed to accept controlled initial state: `SocCommandCenter.js`, `ReconWorkspace.js`, `ResponseRegistryPanel.js`, `IncidentsPanel.js`, `ApprovalsPanel.js`, `PlaybooksPanel.js`, `SoarQueuePanel.js`, `ThreatHuntPanel.js`, and `LiveLogsPanel.js`
- Tests beside the changed modules
- README or behavior docs for analyst navigation controls

## Verification Strategy

- Unit-test stack push/back/forward/dedupe/clear logic.
- Component-test `TopBar` disabled/enabled Back/Forward controls.
- App-level tests for sidebar navigation, alert pivot, related-alert pivot, incident pivot, registry pivot, recon history pivot, browser `popstate`, forward-stack clearing, login/logout clearing, and role visibility fallback.
- Panel tests for restored selected IDs, filters, pagination, tabs/views, expanded rows, and scroll target handling.
- Run `cd frontend && CI=true npm test -- --runInBand --watchAll=false <affected tests>`, `cd frontend && npm run build`, `git diff --check`, and OpenSpec strict validation.
- Perform local browser verification for header controls, cross-workspace restoration, browser Back/Forward, responsive header layout, and preserved scroll/detail state.

## Rollback Strategy

Rollback is frontend-only: remove the workspace history helper, remove TopBar controls, and route all navigation back through the existing `navigateWorkspace` and `SidebarLayout` request behavior. Because no backend, schema, or production data changes are introduced, rollback does not require migrations or data cleanup.

## Documentation Updates

Add a short analyst-facing README or behavior note describing the Back/Forward controls, what context is restored, and when history clears. No AGENTS.md or Mac/VM policy changes are required.

## Blockers / Concerns

- Some panels own local selection/filter/tab state and may need small controlled-state adapters.
- Browser `popstate` must avoid loops with programmatic Back/Forward buttons.
- Scroll restoration can only be best-effort when data reloads or filters remove the original target.
- Runtime browser verification is required after implementation because this is an interaction-heavy UX change.
