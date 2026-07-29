## ADDED Requirements

### Requirement: Unified Anakin command surface orchestrates existing AI capabilities
The UI SHALL provide one primary Anakin command surface that orchestrates existing AI capabilities without duplicating competing AI workflows.

#### Scenario: Analyst opens the primary Anakin surface
- **WHEN** an analyst opens the Anakin command surface from the shell or a contextual AI affordance
- **THEN** the surface presents registry-backed actions for Ask Anakin, Summarize, Investigate, Explain, Draft, and Suggested Actions
- **AND** the surface uses analyst-experience-foundation primitives, dark SOC styling, and blue/cyan AI semantics

#### Scenario: Contextual AI buttons use shared orchestration
- **WHEN** an existing contextual AI button is rendered on dashboard, recon, incident, or SOC command center surfaces
- **THEN** the button remains available where appropriate
- **AND** invoking it routes through the shared command registry and orchestrator instead of a separate command path

#### Scenario: Missing context is handled honestly
- **WHEN** a command requires a selected alert, incident, source IP, recon activity, or visible data that is unavailable
- **THEN** the UI disables the command or explains the missing context
- **AND** it does not fabricate operational facts or selected objects

### Requirement: AI command architecture is reusable and read-safe
The frontend SHALL define one reusable AI command model, action registry, context provider pattern, and command orchestrator.

#### Scenario: Commands share one model
- **WHEN** an Anakin action or palette action is registered
- **THEN** it uses a stable command model with id, label, group, intent, read-only safety, context requirements, availability, and execute behavior
- **AND** command availability can be filtered by role, active section, selected object, and loaded data

#### Scenario: Existing AI routes are reused
- **WHEN** a command executes an AI-backed action
- **THEN** it invokes existing AI service/routes where possible
- **AND** the change does not require backend AI redesign, new LLM providers, or new AI persistence

#### Scenario: Context is sanitized before AI execution
- **WHEN** command context is assembled for AI execution
- **THEN** it includes only relevant workspace, object, data, and user-role context
- **AND** secrets, infrastructure details, and unrelated state are excluded

### Requirement: Global command palette supports read-oriented analyst workflows
The UI SHALL support Cmd/Ctrl+K command palette behavior for navigation, lookup, filters, common analyst actions, and Ask Anakin.

#### Scenario: Analyst opens and closes the palette with keyboard
- **WHEN** an analyst presses Cmd+K or Ctrl+K
- **THEN** the command palette opens with focus in search
- **AND** pressing Escape closes it and returns focus sensibly

#### Scenario: Palette supports read-oriented commands
- **WHEN** the analyst searches the palette
- **THEN** results may include section navigation, object search, IP lookup, incident lookup, alert lookup, recon lookup, Ask Anakin, common analyst actions, and quick filters
- **AND** results are grouped with labels and secondary metadata

#### Scenario: Palette does not expose privileged mutations
- **WHEN** palette results are built
- **THEN** privileged mutations, approval execution, block actions, retries, destructive operations, and production-affecting actions are omitted or disabled
- **AND** read-only safety is enforced by the command registry

### Requirement: Threat Brief identifies current analyst attention priorities
The UI SHALL provide a reusable Threat Brief surface that answers “What requires my attention right now?” using existing authoritative data where possible.

#### Scenario: Threat Brief renders deterministic priority sections
- **WHEN** sufficient data is available
- **THEN** the brief can show highest priority incident, riskiest source IP, pending approvals, automation failures, active investigations, and recommended next action
- **AND** each section distinguishes status, severity, freshness, and source context when available

#### Scenario: Threat Brief avoids duplicate business logic
- **WHEN** Threat Brief derives content
- **THEN** it reuses existing service results, frontend derivation helpers, grouped operations feed inputs, and dashboard/SOC command center data where possible
- **AND** it does not introduce incompatible definitions of incident priority, risk, approval state, or automation failure

#### Scenario: Threat Brief handles incomplete data safely
- **WHEN** some briefing data is loading, empty, stale, or unavailable
- **THEN** the brief renders clear loading, empty, stale, or partial-error states
- **AND** recommended next action is omitted or labeled unavailable rather than invented

### Requirement: Future analyst workflow extension points are defined but not implemented
The command architecture SHALL define extension points for future workflow phases without implementing out-of-scope features.

#### Scenario: Analyst Workspace extension point exists
- **WHEN** future Analyst Workspace work needs AI or palette commands
- **THEN** it can register commands such as pin, draft hypothesis, or create task through the shared command model
- **AND** this phase does not add workspace persistence, workspace data model, or workspace UI

#### Scenario: Investigation and story extensions can reuse context
- **WHEN** future Investigation Drawer or Threat Story work needs selected object, timeline, or correlation context
- **THEN** it can consume the same context provider pattern
- **AND** this phase does not implement those views

### Requirement: Anakin phase preserves foundation and existing workflows
Implementation SHALL build on analyst-experience-foundation without changing its architecture or broadening scope.

#### Scenario: Foundation shell and theme remain intact
- **WHEN** Anakin command surface, palette, or Threat Brief are added
- **THEN** they reuse foundation breakpoints, shell behavior, theme tokens, and primitives
- **AND** they do not redesign the shell, theme, sidebar, or login experience

#### Scenario: Existing workflows remain functional
- **WHEN** implementation is complete
- **THEN** existing dashboard, recon, incident, SOC command center, workspace history, and contextual AI affordances remain functional
- **AND** focused frontend tests and production build pass
