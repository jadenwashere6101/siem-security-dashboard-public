## ADDED Requirements

### Requirement: Threat Brief is scoped to Dashboard
The UI SHALL render the Threat Brief only at the top of the Dashboard page.

#### Scenario: Analyst opens Dashboard
- **WHEN** an analyst or super admin opens the Dashboard section
- **THEN** the Threat Brief appears above the Dashboard content
- **AND** the Dashboard alerts, metrics, charts, filters, and selected-alert behavior remain available

#### Scenario: Analyst opens another section
- **WHEN** an analyst or super admin opens any non-Dashboard section
- **THEN** the Threat Brief is not rendered as global shell content
- **AND** the section starts with its own relevant content rather than Dashboard briefing content

### Requirement: Threat Brief cards handle long text
Threat Brief cards SHALL keep all labels, values, metadata, chips, and recommendations inside their card bounds across supported responsive widths.

#### Scenario: Threat Brief contains long alert and source values
- **WHEN** Threat Brief renders long alert types, source IPs, object identifiers, or recommendations
- **THEN** the text wraps or otherwise remains contained within its card
- **AND** sibling cards, chips, and grid columns do not overlap or force horizontal page overflow

#### Scenario: Threat Brief renders on narrow viewport
- **WHEN** the Dashboard is rendered at mobile or tablet width
- **THEN** Threat Brief cards reflow without clipping or escaping their container
- **AND** unavailable, stale, partial-error, and recommendation states remain readable

### Requirement: Investigation Drawer opens as the only active modal from Alert Details
Opening Investigation Drawer from Alert Details SHALL close or replace Alert Details so only one modal/dialog surface is active.

#### Scenario: Analyst opens drawer from Alert Details
- **WHEN** an analyst opens Alert Details for a selected alert and then chooses Open Investigation Drawer
- **THEN** Alert Details is closed or replaced
- **AND** Investigation Drawer opens with the selected alert context preserved
- **AND** only one `aria-modal` dialog or equivalent modal surface is active

#### Scenario: Drawer focus and close behavior are preserved
- **WHEN** Investigation Drawer is opened from Alert Details
- **THEN** focus moves into the drawer
- **AND** Escape or backdrop close closes the drawer
- **AND** focus returns to the initiating control when available or to a sensible selected-alert/dashboard fallback

#### Scenario: Drawer remains responsive
- **WHEN** Investigation Drawer is opened on desktop, tablet, or mobile
- **THEN** it uses viewport-safe side-panel or full-width overlay behavior
- **AND** drawer scrolling is contained without leaving another modal visible behind it

### Requirement: Sidebar order places Live Logs above Settings
The sidebar SHALL present SOAR and Administration groups above Live Logs, and Live Logs SHALL appear directly above Settings.

#### Scenario: Super admin sidebar renders all groups
- **WHEN** a super admin views the sidebar
- **THEN** SOAR and Administration appear above the Live Logs group
- **AND** Live Logs appears directly above Settings
- **AND** the six ingestion-source Live Logs entries remain grouped together

#### Scenario: Sidebar navigation state is preserved
- **WHEN** an analyst navigates to a Live Logs destination or restores workspace history
- **THEN** navigation uses the same section IDs and history state as before
- **AND** only presentation order changes

### Requirement: Visible version labels are removed
The UI SHALL remove visible application version labels from the login page and sidebar without changing package or application version metadata.

#### Scenario: Login page renders
- **WHEN** the unauthenticated login page renders
- **THEN** it does not display the package version label
- **AND** the login identity, form, error state, and product context remain visible

#### Scenario: Authenticated sidebar renders
- **WHEN** the authenticated sidebar renders in expanded or overlay mode
- **THEN** it does not display the package version label
- **AND** the operational status label may remain visible if still useful

### Requirement: Analyst Workspace quick defects are remediated
Analyst Workspace SHALL handle long private workspace text and expose delete controls for notes, hypotheses, and tasks using existing APIs.

#### Scenario: Workspace renders long private records
- **WHEN** notes, hypotheses, tasks, pins, saved investigations, or evidence references contain long text or identifiers
- **THEN** the text remains inside its card or row
- **AND** the workspace does not create horizontal overflow or overlapping controls

#### Scenario: Analyst deletes private note
- **WHEN** an analyst deletes a note from Analyst Workspace
- **THEN** the UI calls the existing note delete API/service for that note
- **AND** the note is removed from refreshed private workspace state
- **AND** no underlying alert, incident, SOAR, detection, or system event state is mutated

#### Scenario: Analyst deletes private hypothesis
- **WHEN** an analyst deletes a hypothesis from Analyst Workspace
- **THEN** the UI calls the existing hypothesis delete API/service for that hypothesis
- **AND** the hypothesis is removed from refreshed private workspace state
- **AND** no underlying alert, incident, SOAR, detection, or system event state is mutated

#### Scenario: Analyst deletes private task
- **WHEN** an analyst deletes a task from Analyst Workspace
- **THEN** the UI calls the existing task delete API/service for that task
- **AND** the task is removed from refreshed private workspace state
- **AND** no underlying alert, incident, SOAR, detection, or system event state is mutated

### Requirement: Save Investigation provides clear state and discoverability
Save Investigation SHALL show loading, success, failure, and duplicate/idempotent outcomes, and saved investigations SHALL be discoverable from Analyst Workspace.

#### Scenario: Analyst saves an investigation
- **WHEN** an analyst chooses Save Investigation for a selected alert, incident, or source IP context
- **THEN** the button or action surface enters a loading/in-progress state until the request completes
- **AND** a successful result tells the analyst the investigation was saved
- **AND** the saved investigation is visible in Analyst Workspace with linked alert, incident, or source-IP context when available

#### Scenario: Save Investigation fails
- **WHEN** Save Investigation fails because of validation, authorization, network, or server error
- **THEN** the UI presents an accessible failure message
- **AND** existing drawer and workspace content remain intact
- **AND** the analyst can retry after the failure state clears or the request is no longer pending

#### Scenario: Investigation already exists
- **WHEN** the analyst tries to save an investigation that is already represented in their private workspace for the same selected context
- **THEN** the UI prevents a duplicate request or reports that the investigation is already saved
- **AND** it does not imply that a new investigation record was created

### Requirement: Workspace and drawer actions provide consistent feedback
Pin, save evidence, save investigation, create, and delete actions in the investigation/workspace workflow SHALL use a consistent visible feedback pattern.

#### Scenario: Action succeeds
- **WHEN** a pin, save evidence, save investigation, create note, create hypothesis, create task, delete note, delete hypothesis, or delete task action succeeds
- **THEN** the UI shows an accessible success/status message
- **AND** the relevant workspace state is refreshed or updated visibly

#### Scenario: Action is already represented
- **WHEN** a pin, save evidence, or save investigation action targets content already saved for the analyst
- **THEN** the UI shows an accessible idempotent/already-exists message
- **AND** no duplicate private workspace item is presented

#### Scenario: Action is in progress
- **WHEN** a workspace or drawer mutation is in progress
- **THEN** the initiating control is disabled, marked busy, or otherwise shows loading state
- **AND** repeated clicks do not create duplicate requests

#### Scenario: Action fails
- **WHEN** a workspace or drawer mutation fails
- **THEN** the UI shows an accessible error message
- **AND** the message distinguishes failure from success, idempotent, and loading states

### Requirement: Settings remains unchanged for this remediation
The Settings section SHALL not add new configuration entries for this remediation unless implementation discovers a legitimate user preference outside the confirmed audit findings.

#### Scenario: Settings is reviewed during implementation
- **WHEN** implementation evaluates Settings for Threat Brief, Anakin, Investigation Drawer, Save Investigation, sidebar ordering, version labels, or workspace delete controls
- **THEN** no new setting is added for these corrections
- **AND** the implementation notes confirm that Settings required no presentation or configuration update

### Requirement: Full Analyst Workspace redesign remains deferred
This change SHALL keep deeper Analyst Workspace redesign ideas out of scope.

#### Scenario: Deferred workspace ideas are encountered
- **WHEN** implementation identifies source-IP watch workflows, deeper note/task/hypothesis associations, major visual redesign, advanced evidence organization, collaboration, case-management, or broader workspace polish
- **THEN** those ideas are recorded only as deferred future design input if needed
- **AND** they are not implemented as part of this remediation

### Requirement: Remediation verification covers focused UX behavior
Implementation SHALL include focused verification for the confirmed remediation scope.

#### Scenario: Frontend verification runs
- **WHEN** implementation is complete
- **THEN** focused frontend tests cover Threat Brief scope/wrapping, single-overlay drawer behavior, sidebar order, version-label removal, workspace deletion, Save Investigation outcomes, and action feedback
- **AND** the frontend production build passes

#### Scenario: Handoff gates run
- **WHEN** implementation is ready for handoff
- **THEN** dark-theme/accessibility review and practical visual verification are completed
- **AND** `git diff --check` passes
- **AND** `openspec validate post-deployment-ux-remediation --strict` passes
