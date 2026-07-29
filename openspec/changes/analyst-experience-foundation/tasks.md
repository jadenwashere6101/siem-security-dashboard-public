## 1. Foundation Audit and Boundaries

- [x] 1.1 Inventory shell, login, sidebar, topbar, dashboard, and operational feed inline styles that are in scope for incremental migration.
- [x] 1.2 Confirm out-of-scope AI command surface, command palette, Threat Brief, investigation drawer, Threat Story, Analyst Workspace, persistence, and backend workflow changes remain untouched.
- [x] 1.3 Define implementation breakpoints for mobile, tablet, and desktop in one shared frontend location.

## 2. Design Tokens and Primitives

- [x] 2.1 Add shared theme tokens for dark SOC surfaces, spacing, typography, borders, focus states, severity tones, status tones, and AI accent tones.
- [x] 2.2 Add reusable primitives for cards, panels, section headers, buttons, icon buttons, chips, badges, severity/status pills, and compact indicators.
- [x] 2.3 Add focused tests or snapshot-style assertions for token-driven primitive rendering and accessible labels.

## 3. Responsive Shell and Login

- [x] 3.1 Update the application shell so desktop behavior remains functionally unchanged.
- [x] 3.2 Add mobile overlay/collapsible sidebar behavior with backdrop, keyboard support, focus return, and no content clipping.
- [x] 3.3 Add tablet behavior that avoids sidebar/topbar/content overlap.
- [x] 3.4 Make the top bar responsive so session controls, history controls, and workspace title remain usable.
- [x] 3.5 Modernize the login screen with responsive sizing, product identity, optional subtle tactical texture, and sanitized status/version placement.
- [x] 3.6 Add focused frontend tests for login sizing, mobile sidebar behavior, topbar controls, and desktop preservation.

## 4. Dashboard Hierarchy

- [x] 4.1 Migrate dashboard metric cards and section headers to the new primitives without changing dashboard API behavior.
- [x] 4.2 Add reusable trend, freshness, confidence, severity-border, compact summary, and “Why this matters” presentation patterns.
- [x] 4.3 Ensure unknown or unavailable trend/confidence/freshness data is omitted or labeled clearly instead of inferred.
- [x] 4.4 Add focused tests for dashboard hierarchy rendering and non-fabrication of unavailable indicators.

## 5. Grouped Live Operations Feed

- [x] 5.1 Define a normalized grouped feed item model for Incident, Worker, Approval, Notification, and Playbook entries.
- [x] 5.2 Implement a reusable grouped feed primitive that supports grouping, status tone, timestamp, related object labels, and optional navigation targets.
- [x] 5.3 Migrate the existing operational feed surface to the shared model without duplicating feed semantics.
- [x] 5.4 Add focused tests for grouping, ordering, status labels, and empty/error states.

## 6. Sidebar Scanability

- [x] 6.1 Add consistent section icons and accessible labels for sidebar navigation.
- [x] 6.2 Improve collapsed mode so active state, labels/tooltips, and footer status remain understandable.
- [x] 6.3 Preserve existing section visibility and RBAC-derived navigation rules.
- [x] 6.4 Add focused tests for icon labels, active state, collapsed rendering, and role-based visibility preservation.

## 7. Verification and Handoff

- [x] 7.1 Run focused frontend tests for shell, login, primitives, dashboard hierarchy, grouped feed, and sidebar behavior.
- [x] 7.2 Run the frontend production build.
- [x] 7.3 Run `git diff --check`.
- [x] 7.4 Run `openspec validate analyst-experience-foundation --strict`.
- [x] 7.5 Perform browser visual verification at desktop, tablet, and mobile widths, including dark-theme/accessibility review.
- [x] 7.6 Confirm no source code outside the approved implementation scope, backend workflows, persistence, VM access, commit, push, deploy, or production mutation occurred.
