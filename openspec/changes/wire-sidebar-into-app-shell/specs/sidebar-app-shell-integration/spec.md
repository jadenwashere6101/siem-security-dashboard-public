## ADDED Requirements

### Requirement: Sidebar Shell Is the Live Navigation
The application SHALL render `SidebarLayout` as its navigation shell for the authenticated view, replacing the previous inline header and pill-button navigation.

#### Scenario: Sidebar renders instead of inline nav
- **WHEN** an authenticated user views the dashboard
- **THEN** navigation SHALL be rendered via `Sidebar` (grouped, collapsible) instead of the previous flat pill-button bar

### Requirement: activeSection Ownership Is Preserved
`App.js` SHALL remain the sole owner of `activeSection` state; the sidebar shell SHALL NOT own or infer it.

#### Scenario: Clicking a nav item updates App.js state, not shell state
- **WHEN** a user clicks a section in the sidebar
- **THEN** `App.js`'s `activeSection` state SHALL update via the existing `setActiveSection` setter, and the corresponding panel SHALL render exactly as it did before this change

### Requirement: Programmatic Navigation Continues to Work
Existing programmatic navigation paths SHALL continue to update `activeSection` and the sidebar's active highlight SHALL reflect the result.

#### Scenario: ThreatHunt view-related-alerts still navigates to Dashboard
- **WHEN** a user triggers "view related alerts" from the Threat Hunt panel
- **THEN** `activeSection` SHALL become `dashboard`, the Dashboard panel SHALL render with the source-IP search applied, and the sidebar SHALL highlight `dashboard` as active

#### Scenario: SOC Command Center internal navigation still works
- **WHEN** `SocCommandCenter` invokes its `onNavigate` callback
- **THEN** `activeSection` SHALL update accordingly and the sidebar SHALL highlight the resulting section as active

### Requirement: Role Visibility Is Preserved
Section visibility in the sidebar SHALL match the existing `sectionsConfig`-driven visibility exactly for `viewer`, `analyst`, and `super_admin` roles.

#### Scenario: Role-gated sections are unchanged
- **WHEN** a user with a given role views the sidebar
- **THEN** the set of visible sections SHALL be identical to the set that was visible in the previous inline nav for that same role

### Requirement: TopBar Carries Identity and Logout Controls
The application's identity display, role badge, and logout control SHALL render inside `TopBar`'s slot via a new, additive `topBarActions` prop on `SidebarLayout`.

#### Scenario: Identity and logout render and function in TopBar
- **WHEN** an authenticated user views the dashboard
- **THEN** `TopBar` SHALL display the signed-in username and role badge and SHALL provide a working logout control that ends the session exactly as before

#### Scenario: topBarActions is additive and optional
- **WHEN** `SidebarLayout` is used without a `topBarActions` prop
- **THEN** it SHALL render exactly as it did before this change, with no error and no empty visual gap beyond an empty slot

### Requirement: Eyebrow Micro-Label Is Not Silently Dropped
The existing "SIEM" eyebrow micro-label SHALL be preserved via a new, additive, optional `eyebrow` prop on `TopBar` (forwarded through `SidebarLayout`), unless doing so requires more than a minimal prop-and-render-line addition.

#### Scenario: Eyebrow renders via a minimal addition
- **WHEN** `TopBar` receives an `eyebrow` prop
- **THEN** it SHALL render that label above `title`, matching the prior visual treatment, without any other change to `TopBar`'s structure or contract

#### Scenario: Scope ceiling triggers a stop-and-report instead of a workaround
- **WHEN** preserving the eyebrow is found to require restructuring `TopBar`, changing its title contract beyond adding one sibling element, or touching `Sidebar`
- **THEN** implementation SHALL stop and report this instead of expanding scope, and dropping the eyebrow with that report SHALL be treated as an acceptable outcome, not a failure

### Requirement: Existing Runtime Behavior Is Unaffected by Shell Wiring
Authentication flow, alert polling, and panel content-gating SHALL be unaffected by the navigation shell change.

#### Scenario: Polling continues regardless of active section
- **WHEN** a user is authenticated
- **THEN** the existing 5-second alert-polling interval SHALL continue to run regardless of which section is active or how the sidebar's collapse state changes

#### Scenario: Login and logout flows are unchanged
- **WHEN** a user logs in or logs out
- **THEN** the existing pre-authentication screens and logout behavior SHALL be unaffected by the sidebar shell integration

### Requirement: No New Routing or Dependencies
This change SHALL NOT introduce `react-router-dom`, URL-based navigation, or any new npm dependency.

#### Scenario: Dependency manifest and URL behavior are unchanged
- **WHEN** this change is implemented
- **THEN** `frontend/package.json`/lockfile SHALL show no added dependencies, and the application SHALL remain a single-URL SPA
