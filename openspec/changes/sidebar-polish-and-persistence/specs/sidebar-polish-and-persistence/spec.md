## ADDED Requirements

### Requirement: Sidebar Collapse Preference Persists Across Reloads
The sidebar's collapsed/expanded state SHALL persist across page reloads via a dedicated, storage-backed utility.

#### Scenario: Collapsed preference is restored on reload
- **WHEN** a user collapses the sidebar and the page is later reloaded
- **THEN** the sidebar SHALL initialize in the collapsed state

#### Scenario: Expanded preference is restored on reload
- **WHEN** a user expands the sidebar and the page is later reloaded
- **THEN** the sidebar SHALL initialize in the expanded state

### Requirement: Persistence Fails Safe
Reading or writing the sidebar collapse preference SHALL NOT throw or crash the application, regardless of storage availability or data validity.

#### Scenario: No stored preference defaults to expanded
- **WHEN** no collapse preference has been stored
- **THEN** the sidebar SHALL initialize expanded, matching its pre-existing default

#### Scenario: Corrupt stored data is ignored, not coerced
- **WHEN** the stored preference value is missing, malformed, or not a strict boolean
- **THEN** the sidebar SHALL initialize expanded, as if no preference were stored, without throwing

#### Scenario: Storage access failure is swallowed
- **WHEN** reading or writing the preference throws (e.g., storage disabled or unavailable)
- **THEN** the application SHALL continue to render normally, defaulting to expanded, with no unhandled error

### Requirement: Persistence Does Not Change the Component Contract
Collapse-state persistence SHALL be implemented as internal behavior; no new prop SHALL be added to `SidebarLayout`'s public contract for this purpose.

#### Scenario: SidebarLayout usage is unaffected
- **WHEN** `SidebarLayout` is used exactly as it was before this change
- **THEN** it SHALL behave identically apart from the new persistence behavior itself

### Requirement: Footer Status/Version Display Is Finalized for This Spec
This spec SHALL finalize the current static status/version implementation and its polish; the sidebar's bottom status/version panel SHALL render its caller-supplied values with defensive fallback handling, and SHALL NOT be backed by any new health-check API or polling mechanism. Future enhancements to this footer (e.g., backend health indicators or richer build/version information) remain out of scope for this spec but are not precluded from being proposed and built in a later change.

#### Scenario: Truncated footer text remains inspectable
- **WHEN** the footer's status or version text is visually truncated
- **THEN** the corresponding element SHALL carry a `title` attribute with its full text

#### Scenario: Missing footer values render no broken row
- **WHEN** `statusLabel` or `versionLabel` is not supplied
- **THEN** the footer SHALL render without an empty or broken row for that value

#### Scenario: No new backend dependency is introduced
- **WHEN** this change is implemented
- **THEN** no backend health-check endpoint, polling loop, or new npm dependency SHALL be added

### Requirement: No Unrelated Changes
This change SHALL be confined to the sidebar collapse-persistence utility and the footer polish described above.

#### Scenario: Scope is limited to the listed files
- **WHEN** this change is implemented
- **THEN** `frontend/src/App.js`, all panel components, all services, and routing behavior SHALL remain unmodified
