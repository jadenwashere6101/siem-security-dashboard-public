## ADDED Requirements

### Requirement: Destination-aware workspace navigation
The frontend SHALL route every sidebar and programmatic workspace change through one destination-aware contract targeting the actual scrollable main container.

#### Scenario: Ordinary workspace navigation
- **WHEN** a user selects a sidebar workspace or an ordinary SOC Command Center workspace action
- **THEN** the target workspace SHALL render at its top and keyboard focus SHALL move to its primary heading without retaining the prior workspace offset

#### Scenario: Missing deep target
- **WHEN** a requested element destination cannot be rendered
- **THEN** navigation SHALL fall back to the target workspace top and SHALL NOT remain at an unrelated prior offset

### Requirement: Intentional deep destinations
The frontend SHALL preserve explicit filtered and correlated destinations separately from ordinary top navigation.

#### Scenario: Related alerts destination
- **WHEN** a user opens related alerts for a source IP
- **THEN** Dashboard SHALL preserve the source-IP filter and focus/scroll the Recent Alerts destination rather than the workspace top

#### Scenario: Response Registry destination
- **WHEN** a user opens Response Registry with source-IP, alert, incident, or view context
- **THEN** the registry SHALL preserve that context and focus the corresponding registry region

### Requirement: Accessible responsive detail regions
Incident, Playbook definition/execution, and SOAR Operations selections SHALL display in a responsive master-detail region with deterministic focus.

#### Scenario: Desktop selection
- **WHEN** a user selects View on a supported desktop layout
- **THEN** the selected detail SHALL appear adjacent to the list, be identifiable by an accessible heading, and receive focus without requiring page-bottom scrolling

#### Scenario: Narrow viewport selection
- **WHEN** a user selects View where the master-detail layout stacks
- **THEN** the detail SHALL appear immediately after the list region and SHALL be scrolled and focused into view

#### Scenario: Detail close
- **WHEN** a user closes a selected detail
- **THEN** focus SHALL return to the invoking control when it remains available

### Requirement: Motion and refresh safety
Navigation effects SHALL respect reduced-motion preference and SHALL not run for background data refreshes.

#### Scenario: Background refresh
- **WHEN** an open workspace refreshes metrics or records without an explicit navigation action
- **THEN** the frontend SHALL preserve the analyst's current scroll and focus

#### Scenario: Reduced motion
- **WHEN** the user prefers reduced motion
- **THEN** destination scrolling SHALL avoid animated movement

