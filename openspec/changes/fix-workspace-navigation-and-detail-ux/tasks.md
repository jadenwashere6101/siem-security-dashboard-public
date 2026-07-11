## 1. MAC AI — Navigation Contract Pass

- [ ] 1.1 Audit every `setActiveSection`, `onNavigate`, sidebar action, SOC attention action, `Open in…`, related-alert, and Response Registry transition and record its intended destination.
- [ ] 1.2 Add a structured navigation-request utility with `sectionId`, destination kind, optional target key/context, and nonce validation.
- [ ] 1.3 Expose the actual `SidebarLayout` main scroll container and workspace-heading/deep-target refs without using `window.scrollTo`.
- [ ] 1.4 Route ordinary sidebar and SOC Command Center navigation through top-scroll and heading-focus behavior.
- [ ] 1.5 Route Recent Alerts, Response Registry, approval-filter, and other intentional deep links through element destinations while preserving existing state.
- [ ] 1.6 Respect reduced motion and fall back to workspace top when a deep target is unavailable.

## 2. MAC AI — Detail UX Pass

- [ ] 2.1 Implement a reusable responsive master-detail layout/focus helper using existing React/CSS patterns and no new routing dependency.
- [ ] 2.2 Move SOAR Incident detail into the master-detail pattern and restore focus on close.
- [ ] 2.3 Move Playbook definition and execution detail into the master-detail pattern and restore focus on close.
- [ ] 2.4 Move SOAR Operations/Dead Letter detail into the master-detail pattern and restore focus on close.
- [ ] 2.5 Preserve loading, error, action, RBAC, correlation, and canonical outcome states in every moved detail.

## 3. MAC AI — Automated Verification Pass

- [ ] 3.1 Add shell/App tests proving ordinary navigation resets the actual main container and focuses the workspace heading.
- [ ] 3.2 Add tests proving background refresh and same-workspace state updates do not steal scroll/focus.
- [ ] 3.3 Add tests for SOC Command Center, related-alert, Response Registry, approval, incident, playbook, and SOAR Operations transitions.
- [ ] 3.4 Add tests proving deep-link filters/IDs survive and missing targets fall back safely.
- [ ] 3.5 Add component tests for adjacent/stacked detail placement, focus on View, close-focus restoration, and loading/error states.
- [ ] 3.6 Run focused suites, all affected frontend regression suites, and `npm run build`.

## 4. MAC AI — Visual, Accessibility, and Handoff Pass

- [ ] 4.1 Verify keyboard-only navigation, visible focus, heading semantics, close behavior, and reduced-motion behavior.
- [ ] 4.2 Verify dark theme and representative desktop, 1280px, tablet, and narrow/mobile viewports with visual evidence when practical.
- [ ] 4.3 Verify no top bar obscures focused headings/details and no horizontal overflow is introduced.
- [ ] 4.4 Run `openspec validate fix-workspace-navigation-and-detail-ux --strict` and `git diff --check`.
- [ ] 4.5 Prepare a frontend-only deployment handoff identifying the approved commit/artifact requirement and previous-artifact rollback; do not deploy without explicit authorization.

## 5. MAC AI — Stop Conditions

- [ ] 5.1 Stop if any navigation loses filters, correlation IDs, RBAC behavior, or the ability to return to the invoking record.
- [ ] 5.2 Stop if implementation requires React Router, an API/schema change, or VM source modification without a separately approved change.
