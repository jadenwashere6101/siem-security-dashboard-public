## ADDED Requirements

### Requirement: Responsive shell preserves desktop workflow
The application shell SHALL support desktop, tablet, and mobile viewports while preserving the current desktop navigation workflow.

#### Scenario: Desktop navigation remains unchanged
- **WHEN** an analyst uses the application at desktop width
- **THEN** the sidebar, top bar, workspace navigation, history controls, and main content behavior remain functionally equivalent to the current desktop workflow
- **AND** no existing workspace becomes inaccessible because of responsive shell changes

#### Scenario: Mobile sidebar opens as an overlay
- **WHEN** an analyst uses the application at mobile width
- **THEN** the sidebar defaults to a closed or non-obstructive state
- **AND** opening navigation presents an overlay or equivalent mobile navigation surface
- **AND** the main content is not squeezed, clipped, or overlapped by the sidebar

#### Scenario: Tablet layout avoids overlap
- **WHEN** the viewport is between mobile and desktop widths
- **THEN** the shell uses a collapsed rail, overlay, or responsive layout that avoids top bar, sidebar, and content overlap
- **AND** primary navigation remains reachable by keyboard and pointer

### Requirement: Login experience is responsive and professional
The login screen SHALL fit supported viewport widths and present professional SIEM product identity without gimmicky decoration.

#### Scenario: Login fits mobile viewport
- **WHEN** the login screen is rendered at mobile width
- **THEN** the login panel, inputs, and button fit within the viewport without horizontal clipping
- **AND** spacing remains usable with touch targets large enough for mobile interaction

#### Scenario: Login communicates product and system context
- **WHEN** the login screen is rendered
- **THEN** it presents SIEM product identity and may present sanitized system/build/status context
- **AND** any tactical texture or visual motif remains subtle and does not reduce readability

### Requirement: Design tokens and primitives govern new foundation UI
New or migrated foundation UI SHALL use reusable tokens and primitives instead of adding more unrelated inline style systems.

#### Scenario: Semantic tokens define analyst meaning
- **WHEN** components render severity, status, surfaces, spacing, typography, borders, or AI accents
- **THEN** they use shared semantic tokens or primitives
- **AND** red is reserved for critical, danger, failed, destructive, or urgent states
- **AND** blue/cyan is reserved for Anakin-adjacent read-only AI affordances
- **AND** amber is reserved for review, pending, caution, or human-decision states

#### Scenario: Primitives support repeated UI patterns
- **WHEN** cards, panels, buttons, chips, badges, section headers, or status/severity indicators are added or migrated in scope
- **THEN** they use shared reusable primitives
- **AND** the primitives preserve dark SOC readability and accessibility contrast

### Requirement: Dashboard hierarchy helps analysts prioritize
Dashboard hierarchy improvements SHALL communicate analyst priority, freshness, confidence, and why a metric matters when supported by available data.

#### Scenario: Metric hierarchy distinguishes urgency
- **WHEN** dashboard metric cards render severity or operational state
- **THEN** severity borders, status indicators, and compact summaries make the highest-priority work visually scannable
- **AND** decorative styling is not used as a substitute for analyst-relevant meaning

#### Scenario: Unknown data is not overstated
- **WHEN** trend, freshness, confidence, or “Why this matters” data is unavailable
- **THEN** the UI omits the indicator or labels it unavailable
- **AND** it does not fabricate certainty, causality, or operational outcomes

### Requirement: One grouped operational feed model is reusable
Operational feed presentation SHALL use one reusable grouped model for Incident, Worker, Approval, Notification, and Playbook activity.

#### Scenario: Feed groups activity by operational type
- **WHEN** operational feed data is rendered
- **THEN** items are grouped or filterable by Incident, Worker, Approval, Notification, and Playbook
- **AND** each item clearly distinguishes status, time, title, related object, and action target when available

#### Scenario: Duplicate feed implementations are avoided
- **WHEN** a dashboard, SOC command center, or future surface needs operational feed presentation
- **THEN** it consumes the shared feed primitive or normalized feed model
- **AND** it does not reimplement incompatible grouping, tone, or status semantics

### Requirement: Sidebar scanability improves without changing authorization
Sidebar improvements SHALL make navigation faster to scan while preserving existing section visibility and RBAC behavior.

#### Scenario: Sidebar uses icons and grouping consistently
- **WHEN** the sidebar renders visible sections
- **THEN** icons, section groups, labels, active state, and collapsed affordances are consistent and accessible
- **AND** role-based visibility remains governed by the existing section visibility rules

#### Scenario: Collapsed sidebar remains understandable
- **WHEN** the sidebar is collapsed on desktop or tablet
- **THEN** visible icon-only or compact controls expose accessible names and tooltips or equivalent labels
- **AND** active workspace state remains perceivable

### Requirement: Foundation verification covers responsive, accessibility, and build behavior
Implementation SHALL include focused verification for the UX foundation.

#### Scenario: Automated and visual checks cover the shell
- **WHEN** implementation is complete
- **THEN** focused frontend tests cover responsive sidebar/topbar/login behavior and primitive rendering
- **AND** browser visual verification covers desktop, tablet, and mobile widths

#### Scenario: Accessibility and build gates pass
- **WHEN** implementation is complete
- **THEN** keyboard navigation, focus behavior, labels, contrast, reduced motion, and touch targets are reviewed
- **AND** the frontend production build, `git diff --check`, and strict OpenSpec validation pass
