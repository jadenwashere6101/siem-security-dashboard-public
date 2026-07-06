## ADDED Requirements

### Requirement: Isolated Sidebar Shell Components
The system SHALL provide `SidebarLayout`, `Sidebar`, and `TopBar` React components that render a grouped, collapsible navigation shell from caller-supplied data, without being wired into any existing application file.

#### Scenario: Components exist independently of App.js
- **WHEN** this change is implemented
- **THEN** `frontend/src/App.js`, all panel components, and all services SHALL remain unmodified, and the new components SHALL be reachable only through their own tests

### Requirement: Data-Driven Grouped Navigation
The `Sidebar` component SHALL render navigation items from a caller-supplied `sections` array shaped like `sectionsConfig` entries, filtered by each entry's own `visibleWhen(roleFlags)`, and grouped by each entry's `group` field.

#### Scenario: Only visible sections render
- **WHEN** `Sidebar` receives a `sections` array where some entries' `visibleWhen(roleFlags)` returns `false` for the given `roleFlags`
- **THEN** those entries SHALL NOT render as navigation items

#### Scenario: Sections are grouped generically
- **WHEN** `Sidebar` receives visible sections with different `group` values
- **THEN** it SHALL render a heading/label per distinct group value without assuming any specific fixed set of group names

### Requirement: Collapsed and Expanded States
The `Sidebar` and `SidebarLayout` components SHALL support a collapsed and an expanded visual state, toggled via a hamburger button in `TopBar`.

#### Scenario: Toggling the hamburger changes collapse state
- **WHEN** a user activates the hamburger toggle button in `TopBar`
- **THEN** `SidebarLayout`'s collapse state SHALL flip, and `Sidebar`'s rendering SHALL reflect the new state

#### Scenario: Accessible names survive collapse
- **WHEN** `Sidebar` is in its collapsed state
- **THEN** every navigation item SHALL retain an accessible name (via visible text still present in the DOM or an explicit `aria-label`), even if the visible label text is truncated or hidden

### Requirement: Active Section Highlighting
The `Sidebar` component SHALL visually and semantically indicate which section is active, based on a caller-supplied `activeSectionId`.

#### Scenario: Active item is marked for assistive technology
- **WHEN** a navigation item's `id` matches `activeSectionId`
- **THEN** that item SHALL have `aria-current="page"` in addition to any visual highlight styling

### Requirement: Navigation Callback Without State Ownership
The `Sidebar` and `SidebarLayout` components SHALL NOT own or infer `activeSection` state; clicking a navigation item SHALL invoke a caller-supplied `onNavigate(id)` callback.

#### Scenario: Clicking a nav item calls the callback with the correct id
- **WHEN** a user clicks a visible navigation item
- **THEN** `onNavigate` SHALL be called exactly once with that item's `id`, and no internal component state SHALL change to reflect a new "active" section

### Requirement: Bottom Status and Version Panel
The `Sidebar` component SHALL render a bottom status/version panel from caller-supplied props.

#### Scenario: Status and version content renders from props
- **WHEN** `Sidebar` receives status/version footer props
- **THEN** that content SHALL render in a bottom panel area distinct from the navigation items

### Requirement: No New Dependencies or Routing
This change SHALL NOT introduce `react-router-dom`, any icon library, or any other new npm dependency, and SHALL NOT introduce URL-based or history-based navigation behavior.

#### Scenario: Dependency manifest is unchanged
- **WHEN** this change is implemented
- **THEN** `frontend/package.json` and its lockfile SHALL show no added dependencies
