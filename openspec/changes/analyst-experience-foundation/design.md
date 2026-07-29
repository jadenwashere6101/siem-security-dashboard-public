## Context

The React app currently centralizes much workflow orchestration in `App.js` and uses `SidebarLayout`, `TopBar`, `Sidebar`, dashboard components, `SocCommandCenter`, and login JSX as the primary shell surfaces. Many visual decisions are inline style objects, which makes consistency and responsive behavior difficult to enforce. Recent visual inspection showed the mobile login and authenticated shell can clip or overlap content because desktop layout assumptions remain active on narrow screens.

This change is a frontend UX foundation only. It must not introduce new backend workflows, database persistence, Anakin command orchestration, command palette behavior, Threat Brief aggregation, investigation drawer redesign, Threat Story, or Analyst Workspace.

## Goals / Non-Goals

**Goals:**

- Preserve desktop navigation and analyst workflows.
- Make login and authenticated shell usable at mobile, tablet, and desktop widths.
- Introduce reusable UI primitives and design tokens that future UX changes can build on incrementally.
- Improve dashboard hierarchy and operational feed scanability with analyst-useful patterns, not decoration.
- Define regression, accessibility, and performance expectations before implementation.

**Non-Goals:**

- No Sith/red redesign, decorative overhaul, new AI workflow, new command palette, new persistence, backend workflow, schema migration, VM work, or production mutation.

## Reusable Primitives

- **Theme tokens:** color, surface, border, focus, shadow, spacing, typography, radius, z-index, breakpoints, severity tones, status tones, and AI accent tones.
- **Layout primitives:** `AppShell`, `ShellMain`, `ResponsiveTopBar`, `ResponsiveSidebar`, `PageSection`, `SectionHeader`, responsive grid/stack helpers.
- **Surface primitives:** `Card`, `Panel`, `DrawerSurface`, `ToolbarSurface`, `MetricCard`.
- **Controls:** `Button`, `IconButton`, `SegmentedControl`, `SelectField`, `SearchField`, `Chip`, `Badge`, `StatusPill`, `SeverityPill`.
- **Analyst patterns:** `TrendIndicator`, `FreshnessIndicator`, `ConfidenceIndicator`, `WhyThisMatters`, `CompactSummary`, `GroupedOperationsFeed`.

Primitives should be plain React/CSS modules or shared style helpers consistent with the existing codebase. Adding a dependency is not required.

## Responsive Strategy

Use named breakpoints rather than ad hoc widths:

- `mobile`: under 640px. Sidebar defaults closed and opens as an overlay with backdrop; top bar wraps or hides secondary controls; login card uses viewport-safe width.
- `tablet`: 640px to 1023px. Sidebar may be collapsed rail or overlay depending on available width; content spacing tightens; grids reduce columns.
- `desktop`: 1024px and above. Current desktop workflow remains unchanged unless adopting primitives with equivalent behavior.

Focus management must move into the overlay sidebar when open and return to the toggle when closed. Reduced motion preferences must be respected.

## Theme Strategy

Maintain the existing dark SOC base. Define semantic tokens instead of hard-coded palette reuse:

- Graphite/dark surfaces for shell and panels.
- Blue/cyan for AI/Anakin-adjacent read-only affordances.
- Amber for review, pending approval, caution, and human decision states.
- Red only for critical, danger, failed, destructive, or urgent states.
- Green only for healthy, clear, success, or operational states.

Icons should come from an existing approved icon source if one is already available; otherwise implementation should choose the smallest maintainable approach and avoid hand-drawn one-off icons where possible.

## Dashboard Strategy

Dashboard hierarchy improvements should be reusable, compact, and tied to analyst prioritization:

- Metrics can show trend direction, freshness, confidence, severity accent, and a short “Why this matters” line when data supports it.
- Patterns must distinguish real outcome, simulated/tracking-only state, pending, failed, blocked, unknown, and stale.
- Do not fabricate trend/confidence. If data is unavailable, render “unavailable” or omit the indicator.
- Existing dashboard query behavior should remain unchanged unless a later backend spec extends summary data.

## Live Feed Strategy

Create one grouped operational feed presentation model with item type, title, timestamp, status, tone, related object IDs, and optional action target. It should support Incident, Worker, Approval, Notification, and Playbook groups. Existing `SocCommandCenter` feed derivation can inform the model, but implementation should avoid duplicating feed builders across dashboard, SOC command center, and future surfaces.

## Implementation Phases

1. Add tokens and the smallest primitive set needed by shell/login.
2. Make shell/topbar/sidebar/login responsive while preserving desktop behavior.
3. Migrate dashboard cards/headers/indicators to primitives.
4. Introduce grouped feed primitive and use it in existing operational feed surface.
5. Polish sidebar icons/grouping/collapsed behavior using the same primitives.

## Rollout Strategy

Migrate incrementally. Start with shell/login and shared primitives; then convert high-visibility dashboard/feed/sidebar surfaces. Avoid touching unrelated panels unless needed to consume a primitive. Existing inline styles may remain where migration is out of scope.

## Risks

- Desktop workflow regression from shell changes.
- Mobile overlay focus/scroll bugs.
- Token migration creating inconsistent colors if partially applied.
- Reducing visible severity contrast by overusing accent colors.
- Feed grouping accidentally implying state changes instead of read-only presentation.

## Regression Plan

- Focused component tests for sidebar open/collapse/overlay behavior, topbar responsive controls, login viewport sizing, dashboard primitive rendering, and grouped feed output.
- Visual review at desktop, tablet, and mobile widths.
- Accessibility checks for keyboard navigation, focus trapping/return, labels, contrast, reduced motion, and hit targets.
- Frontend production build and `git diff --check`.
- `openspec validate analyst-experience-foundation --strict`.

## Performance Considerations

Keep primitives lightweight. Avoid expensive resize listeners where CSS media queries suffice. Avoid repeated derived feed sorting in render paths; memoize normalized feed items where needed. Do not add large visual dependencies for texture or icons without clear benefit.
