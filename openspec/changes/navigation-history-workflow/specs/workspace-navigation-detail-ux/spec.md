## ADDED Requirements

### Requirement: Workspace investigation history
The frontend SHALL maintain a bounded session-local workspace history that supports Back and Forward through meaningful analyst investigation navigation.

#### Scenario: Meaningful navigation creates history
- **WHEN** an analyst moves between workspaces or opens an alert, incident, source-IP context, recon activity, playbook, approval, queue item, or response registry context
- **THEN** the frontend SHALL record a workspace history entry containing only serializable restoration metadata for that investigation context

#### Scenario: Insignificant UI activity does not flood history
- **WHEN** an analyst types in a search field, changes a filter, changes sort, changes pagination, refreshes data, collapses the sidebar, hovers, or waits for background loading
- **THEN** the frontend SHALL update the current restorable snapshot where appropriate and SHALL NOT create a new Back-stack entry solely for that insignificant action

#### Scenario: Consecutive duplicate destinations are deduped
- **WHEN** an analyst repeats the same navigation destination with equivalent restoration state
- **THEN** the frontend SHALL keep a single current history entry instead of adding a duplicate consecutive entry

#### Scenario: Forward stack clears after new navigation
- **WHEN** an analyst goes Back and then performs a new meaningful navigation
- **THEN** the frontend SHALL clear the Forward stack before recording the new destination

### Requirement: Workspace history controls
The application header SHALL expose analyst-facing Back and Forward controls in the top-left header area.

#### Scenario: Back is available
- **WHEN** the workspace history has a prior entry
- **THEN** the Back control SHALL be enabled and activation SHALL restore the prior investigation context

#### Scenario: Forward is available
- **WHEN** the analyst has moved Back and a forward entry exists
- **THEN** the Forward control SHALL be enabled and activation SHALL restore the next investigation context

#### Scenario: Controls are disabled
- **WHEN** no prior or next workspace history entry exists
- **THEN** the corresponding Back or Forward control SHALL be disabled and SHALL NOT mutate active workspace state

#### Scenario: Header remains usable on narrow screens
- **WHEN** the viewport is narrow
- **THEN** the Back and Forward controls SHALL remain visible, accessible, and non-overlapping with the sidebar toggle, title, and session actions

### Requirement: Investigation state restoration
Workspace history restoration SHALL restore enough context for analysts to continue an investigation without reconstructing their prior view.

#### Scenario: Dashboard alert context restores
- **WHEN** history restores a Dashboard alert investigation entry
- **THEN** the frontend SHALL restore active workspace, selected alert, alert search/filter/sort/pagination values, exact source/target/alert pivots, and the Recent Alerts destination when present

#### Scenario: Incident and SOAR contexts restore
- **WHEN** history restores an incident, approval, playbook, SOAR queue, or Response Registry entry
- **THEN** the frontend SHALL restore the relevant active workspace and supported selected IDs, views, filters, related context, and detail focus using existing panel loading contracts

#### Scenario: Source-IP and recon contexts restore
- **WHEN** history restores a source-IP or recon investigation entry
- **THEN** the frontend SHALL restore the active workspace, selected source IP or recon activity, recon filters/search/sort/pagination, linked-alert pagination where supported, and related alert pivots

#### Scenario: Unsupported local state falls back safely
- **WHEN** a saved entry contains state for a panel that cannot currently restore part of that state
- **THEN** the frontend SHALL restore the supported workspace and target context and SHALL ignore unsupported fields without throwing an error

#### Scenario: Restored data is reloaded, not duplicated
- **WHEN** history restores a previous context
- **THEN** the frontend SHALL reload or reuse normal workspace data flows and SHALL NOT store API result arrays, detail payloads, AI transcript contents, secrets, or large datasets in history entries

### Requirement: Browser Back and Forward integration
The frontend SHALL integrate browser Back and Forward with SIEM workspace history without replacing the current single-page architecture.

#### Scenario: Browser Back restores workspace history
- **WHEN** the browser Back action lands on a SIEM-owned workspace-history state
- **THEN** the frontend SHALL restore the corresponding previous workspace history entry

#### Scenario: Browser Forward restores workspace history
- **WHEN** the browser Forward action lands on a SIEM-owned workspace-history state
- **THEN** the frontend SHALL restore the corresponding next workspace history entry

#### Scenario: Non-SIEM browser state is ignored
- **WHEN** a `popstate` event does not contain a SIEM workspace-history marker
- **THEN** the frontend SHALL NOT attempt to restore SIEM workspace state from that event

#### Scenario: Browser integration avoids feedback loops
- **WHEN** a workspace history entry is restored from Back, Forward, or `popstate`
- **THEN** the frontend SHALL avoid pushing another browser history entry for the same restoration action

### Requirement: History lifecycle and visibility safety
Workspace history SHALL clear or degrade safely when session or role context changes.

#### Scenario: Authentication boundary clears history
- **WHEN** the analyst logs out, switches account, loses authentication, or completes a fresh login
- **THEN** the frontend SHALL clear workspace Back and Forward stacks and initialize history from the new visible landing workspace

#### Scenario: Role visibility changes invalidate entries safely
- **WHEN** a restored entry targets a workspace that is not visible for the current role
- **THEN** the frontend SHALL restore Dashboard instead and SHALL clear invalid selected entity state

#### Scenario: Bounded history limit
- **WHEN** the analyst creates more history entries than the configured maximum
- **THEN** the frontend SHALL discard the oldest entries while preserving the current entry and most recent investigation path

### Requirement: Scroll and focus restoration
Workspace history SHALL restore scroll and focus where practical without breaking existing destination-aware navigation.

#### Scenario: Saved scroll position restores
- **WHEN** a history entry includes a valid main-container scroll position
- **THEN** `SidebarLayout` SHALL restore that scroll position after the workspace renders and SHALL focus the best available heading or detail target

#### Scenario: Missing target falls back
- **WHEN** the saved target or scroll position cannot be applied because data changed or the element no longer exists
- **THEN** the frontend SHALL fall back to existing workspace top or element navigation behavior

#### Scenario: Background refresh remains stable
- **WHEN** background data refreshes occur while viewing a restored workspace
- **THEN** the frontend SHALL preserve the current scroll and focus unless an explicit navigation action requests otherwise
