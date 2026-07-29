## Why

The current SIEM UI has strong analyst functionality, but the shell, dashboard, login screen, feed presentation, and visual primitives are implemented with scattered inline styles and desktop-first assumptions. This makes mobile use unreliable, slows future UX work, and risks inconsistent severity/status presentation across analyst workflows.

## What Changes

- Establish a responsive application shell that preserves the current desktop workflow while adding tablet/mobile behavior, an overlay/collapsible sidebar, responsive top bar, responsive spacing, and a login screen that fits small viewports.
- Introduce reusable frontend design primitives and theme tokens for cards, panels, buttons, chips, badges, spacing, typography, severity/status treatments, icons, and section headers.
- Preserve the existing dark SOC appearance while defining maintainable color semantics: graphite/dark base, blue/cyan for Anakin-adjacent AI affordances, amber for review/pending states, and red only for critical/danger states.
- Improve dashboard information hierarchy through reusable patterns for trend indicators, freshness, confidence, severity borders, compact analyst summaries, and “Why this matters” content.
- Define one reusable grouped Live Operations Feed model for Incident, Worker, Approval, Notification, and Playbook activity so future surfaces do not duplicate feed logic.
- Improve sidebar scanability with icons, clearer grouping, collapsed-mode affordances, and responsive behavior.
- Modernize the login experience with professional product identity, responsive sizing, optional subtle tactical texture, system/build status placement, and no gimmicky theme shift.
- Do not include unified Anakin command surface, command palette, Threat Brief, investigation drawer redesign, Threat Story View, Analyst Workspace, new persistence, or new backend workflows.

## Capabilities

### New Capabilities

- `analyst-experience-foundation`: Covers responsive shell behavior, reusable UI primitives/theme tokens, dashboard hierarchy patterns, grouped operational feed presentation, sidebar scanability, and professional login experience.

### Modified Capabilities

- None.

## Impact

- Frontend architecture: application shell, top bar, sidebar, login rendering, dashboard components, SOC command center/feed presentation, shared UI primitives, and tests.
- Styling approach: incremental migration from inline styles to reusable primitives/tokens without a broad rewrite.
- Backend/API/database: no required backend workflows, API contract changes, database schema changes, persistence, or production runtime changes.
- Verification: focused frontend tests, responsive visual checks at desktop/tablet/mobile widths, accessibility review, production build, `git diff --check`, and strict OpenSpec validation.
