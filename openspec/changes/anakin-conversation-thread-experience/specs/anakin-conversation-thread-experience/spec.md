## ADDED Requirements

### Requirement: One canonical SIEM conversation surface
The SIEM application SHALL mount at most one Anakin conversation response surface, and every global or contextual Anakin entry point SHALL open or focus that surface.

#### Scenario: Contextual and global entry points converge
- **WHEN** an analyst activates Anakin from two different SIEM surfaces
- **THEN** the application focuses the same conversation panel without mounting a duplicate response surface

#### Scenario: Isolated products remain separate
- **WHEN** Repo Assistant or SOC Briefing is opened
- **THEN** neither product is rendered as a mode or turn inside the SIEM conversation surface

### Requirement: Deterministic foreground ownership
The application SHALL allow only one alert-details drawer, Anakin panel, modal investigation drawer, or command palette to own foreground interaction at a time.

#### Scenario: Alert details hands off to Anakin
- **WHEN** an analyst invokes Anakin from the alert-details drawer
- **THEN** the alert identity is preserved, the alert drawer yields foreground, and the Anakin panel is fully visible

#### Scenario: Escape closes only the active layer
- **WHEN** the analyst presses Escape with a foreground layer open
- **THEN** only the top active layer closes and focus returns to an appropriate initiating control

### Requirement: Task-oriented controls
The UI SHALL present one primary freeform Ask action and SHALL describe workflow shortcuts as optional analyst tasks without requiring workflow selection.

#### Scenario: Global question needs no shortcut
- **WHEN** an analyst enters a normal question and submits it without selecting a shortcut
- **THEN** the request uses Ask Anakin auto-routing and appears in the active thread

#### Scenario: Contextual task preserves entity
- **WHEN** an analyst selects Explain, Investigate, Recommend, or Draft from an entity surface
- **THEN** the canonical panel receives the task workflow and that explicit entity

### Requirement: Authoritative thread transcript
The conversation panel SHALL render ordered turns and active state from authenticated PostgreSQL-backed thread APIs, and browser storage SHALL contain only safe pointers.

#### Scenario: Refresh restores conversation and progress
- **WHEN** the page refreshes during or after an asynchronous turn
- **THEN** the panel reloads the authorized thread, ordered turns, and active request state from the server

#### Scenario: Logout clears pointers
- **WHEN** the analyst logs out or the authenticated identity changes
- **THEN** local thread and request pointers are cleared before any later user can render them

### Requirement: Complete thread interaction
The panel SHALL provide ordered turns, active entity, follow-up input, task shortcuts, per-turn progress, clarification, retry, reset, New Thread, remembered-state disclosure, and expired-context recovery.

#### Scenario: Failed turn can be retried
- **WHEN** a generation fails for a stored user turn
- **THEN** the panel shows the failure on that turn and offers a retry using a new idempotent submission

#### Scenario: Reset starts clean replacement
- **WHEN** an analyst resets an active thread
- **THEN** the closed thread is excluded and the replacement thread opens with no prior turns

#### Scenario: Artifact safety survives refresh
- **WHEN** a generated artifact turn is restored
- **THEN** it remains labeled Preview only, Not applied, Not persisted as an operational record, and Approval required before apply

### Requirement: Stale and duplicate response protection
The UI SHALL bind visible progress and completion to the active request, thread, and selection epoch and SHALL prevent duplicate local submission.

#### Scenario: Entity switches before completion
- **WHEN** a previous thread completes after the analyst has selected another thread
- **THEN** the completion does not attach to the newly visible thread

#### Scenario: Shortcut is double-clicked
- **WHEN** an analyst double-clicks a workflow shortcut
- **THEN** only one local submission is issued and backend idempotency remains authoritative

### Requirement: Responsive and accessible interaction
The conversation surface SHALL remain visible and usable at supported desktop and narrow widths without hidden content, incoherent overlap, trapped focus, or incorrect scroll locking.

#### Scenario: Narrow viewport
- **WHEN** the viewport narrows while Anakin is open
- **THEN** the panel fits the viewport, preserves input and transcript access, and does not overlap another foreground surface

#### Scenario: Keyboard operation
- **WHEN** an analyst opens, uses, and closes Anakin by keyboard
- **THEN** focus moves into the active panel, remains operable, and returns on close

### Requirement: Analyst-facing terminology
The conversation UI SHALL use task and outcome language and SHALL NOT expose canonical workflow, auto-routing, guided analysis, workflow request, async request, model/profile routing, or implementation lifecycle vocabulary.

#### Scenario: Progress and results are displayed
- **WHEN** a turn is queued, running, clarified, completed, or failed
- **THEN** the UI describes the analyst-visible state without architecture terminology
