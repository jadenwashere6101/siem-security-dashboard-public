## 1. Workspace History Core

- [x] 1.1 Add `frontend/src/utils/workspaceHistory.js` with bounded stack state, forward stack state, entry normalization, dedupe keys, snapshot validation, and clear/reset helpers.
- [x] 1.2 Add unit tests for push, replace-current, Back, Forward, forward-stack clearing, duplicate suppression, max-entry trimming, and invalid snapshot handling.
- [x] 1.3 Extend `frontend/src/utils/workspaceNavigation.js` to support history metadata and optional restored scroll position without changing existing destination behavior.

## 2. App Integration

- [x] 2.1 Add app-level workspace history state in `App.js` and initialize it after authenticated landing workspace selection.
- [x] 2.2 Route sidebar navigation and programmatic pivots through a history-aware navigation function while preserving existing `navigateWorkspace` behavior.
- [x] 2.3 Capture Dashboard alert state: `alertView`, `selectedAlertId`, exact source/target/alert pivots, sort, pagination, and Recent Alerts target.
- [x] 2.4 Capture supported cross-workspace target state for incidents, approvals, playbooks, SOAR queue, Response Registry, SOC Command Center, Recon History, Threat Hunt, and Live Logs.
- [x] 2.5 Restore saved entries through existing setters and initial request props without storing API result datasets.
- [x] 2.6 Clear history on logout, account switch, failed auth/session loss, fresh login, and role visibility invalidation.

## 3. Browser History Integration

- [x] 3.1 Add SIEM-owned `window.history.state` markers for workspace history entries.
- [x] 3.2 Push browser history entries for meaningful SIEM workspace navigation.
- [x] 3.3 Handle `popstate` to restore matching workspace history entries.
- [x] 3.4 Add loop guards so Back, Forward, and `popstate` restoration do not push duplicate browser states.
- [x] 3.5 Add tests for browser Back, browser Forward, non-SIEM `popstate`, and new-navigation forward-stack clearing.

## 4. UI and Scroll Restoration

- [x] 4.1 Update `TopBar` to accept a top-left navigation controls slot after the sidebar toggle and before the title.
- [x] 4.2 Add compact Back and Forward buttons with accessible labels and correct disabled states.
- [x] 4.3 Update `SidebarLayout` to restore saved main-container scroll position when provided and to fall back to existing top/element behavior when not possible.
- [x] 4.4 Verify responsive header layout so navigation controls do not overlap the sidebar toggle, title, or session actions.
- [x] 4.5 Preserve reduced-motion behavior and background-refresh scroll/focus stability.

## 5. Panel Restoration Adapters

- [x] 5.1 Add controlled or initial-state restoration for SOC Command Center selected incident, selected recon activity, and source-IP drawer only where needed.
- [x] 5.2 Add restoration for Recon History filters, selected recon activity, list pagination, and linked-alert pagination.
- [x] 5.3 Add restoration for Response Registry view/query/exact indicator/related context/selected entry using existing navigation request patterns.
- [x] 5.4 Add restoration for Incidents, Approvals, Playbooks, and SOAR Queue selected IDs and supported view filters using existing initial request patterns.
- [x] 5.5 Add restoration for Threat Hunt and Live Logs filters, pagination, and expanded rows only if it can be done with small controlled-state adapters.

## 6. Tests and Documentation

- [x] 6.1 Add App-level tests for sidebar workspace changes, alert pivots, related-alert pivots, source-IP context, recon history, incident/playbook/approval/registry pivots, and restored selected context.
- [x] 6.2 Add component tests for TopBar controls, SidebarLayout restored scroll, and representative panel restoration adapters.
- [x] 6.3 Add behavior documentation describing workspace Back/Forward controls, restored state, history-clearing boundaries, and best-effort scroll restoration.
- [x] 6.4 Run `cd frontend && CI=true npm test -- --runInBand --watchAll=false <affected tests>`.
- [x] 6.5 Run `cd frontend && npm run build`.
- [x] 6.6 Run `git diff --check`.
- [x] 6.7 Run `openspec validate navigation-history-workflow --strict`.
- [ ] 6.8 Perform local browser verification for Back/Forward controls, browser Back/Forward, cross-workspace pivots, state restoration, responsive header layout, and scroll restoration.
- [x] 6.9 Document rollback notes and VM sync/runtime browser verification requirements in the implementation handoff.
