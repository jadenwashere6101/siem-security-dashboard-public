## ADDED Requirements

### Requirement: Display Settings Extend The Shared Settings Module
The frontend SHALL store all display preferences defined by this spec as a `display` section within the same shared, localStorage-backed settings object introduced by `siem-settings-foundation`, rather than a separate storage key or mechanism.

#### Scenario: Display settings share one storage key
- **WHEN** display preferences are read or written
- **THEN** they SHALL use the same localStorage key and settings object as `siem-settings-foundation`'s settings module.

#### Scenario: Unknown display keys do not break other settings
- **WHEN** localStorage contains an unknown key within `display`
- **THEN** the frontend SHALL ignore the unknown key and continue using all other known settings.

### Requirement: Timezone Preference
The frontend SHALL allow the user to choose whether displayed timestamps use the browser's local timezone or a fixed UTC timezone, and SHALL apply that choice to every displayed timestamp.

#### Scenario: Local browser timezone is the default and recommended option
- **WHEN** no timezone preference has been stored
- **THEN** the frontend SHALL display timestamps in the browser's local timezone.

#### Scenario: Selecting UTC changes every displayed timestamp
- **WHEN** the user selects UTC
- **THEN** every timestamp rendered through the shared timestamp helper across Alerts, Events, Live Logs, and Incident views SHALL display in UTC.

#### Scenario: Selecting local timezone changes every displayed timestamp
- **WHEN** the user selects local browser timezone
- **THEN** every timestamp rendered through the shared timestamp helper across Alerts, Events, Live Logs, and Incident views SHALL display in the browser's local timezone.

### Requirement: Timestamp Format Preference
The frontend SHALL allow the user to choose between 12-hour and 24-hour timestamp formatting, and SHALL apply that choice consistently to every displayed timestamp.

#### Scenario: 24-hour format is the default
- **WHEN** no timestamp format preference has been stored
- **THEN** the frontend SHALL display timestamps in 24-hour format.

#### Scenario: Format preference applies everywhere consistently
- **WHEN** the user changes the timestamp format preference
- **THEN** every surface consuming the shared timestamp helper SHALL reflect the new format with no surface left showing the previous format.

### Requirement: Shared Timestamp Helper Replaces Fragmented Formatting
The frontend SHALL provide one shared, settings-aware timestamp formatting helper used by every timestamp-displaying surface in scope, replacing independent per-component timestamp formatting logic.

#### Scenario: Previously raw timestamp surfaces become formatted
- **WHEN** a surface that previously rendered an unformatted raw timestamp string (Alerts, Live Logs) is rendered under any timezone/format setting, including defaults
- **THEN** it SHALL display a timestamp formatted through the shared helper rather than a raw string.

#### Scenario: Invalid timestamp values render a safe fallback
- **WHEN** a timestamp value is missing, malformed, or unparseable
- **THEN** the shared helper SHALL render a safe fallback value and SHALL NOT throw or render "Invalid Date".

### Requirement: Rows Per Page / Event Limit Is Frontend-Only
The frontend SHALL allow the user to choose how many already-fetched rows are rendered in supported tables, without changing any backend query, endpoint, or response limit.

#### Scenario: Default shows all fetched rows
- **WHEN** no rows-per-page/event limit preference has been stored
- **THEN** supported tables SHALL render every already-fetched row exactly as they do today, with no truncation.

#### Scenario: Selecting a numeric limit truncates rendered rows only
- **WHEN** the user selects a numeric rows-per-page/event limit
- **THEN** supported tables SHALL render only that many rows from their already-fetched, already-filtered/sorted data, and no request, query parameter, or API contract SHALL change as a result.

### Requirement: Live Logs Font Size Preference
The frontend SHALL allow the user to choose a Live Logs font size, and SHALL apply the change immediately.

#### Scenario: Default preserves current Live Logs font size
- **WHEN** no Live Logs font size preference has been stored
- **THEN** Live Logs SHALL render with exactly its current, existing font sizes.

#### Scenario: Font size updates immediately
- **WHEN** the user changes the Live Logs font size preference while Live Logs is open
- **THEN** the displayed font size SHALL update without requiring a page reload.

### Requirement: Default Live Logs Tab Preference
The frontend SHALL allow the user to choose which Live Logs tab (Event Feed, Raw Log, or JSON) is selected when Live Logs is opened, and SHALL persist that choice across sessions.

#### Scenario: Default preserves current initial tab
- **WHEN** no default Live Logs tab preference has been stored
- **THEN** Live Logs SHALL open on the Event Feed tab, matching current behavior.

#### Scenario: Default tab persists across sessions
- **WHEN** a user sets a default Live Logs tab and later reopens Live Logs in a new session
- **THEN** Live Logs SHALL open on the previously selected default tab.

#### Scenario: Manual tab switching during a session is unaffected
- **WHEN** a user manually switches tabs while Live Logs is open
- **THEN** manual switching SHALL continue to work exactly as it does today, independent of the stored default.

### Requirement: Severity Color Presets
The frontend SHALL allow the user to choose among named severity color presets, applied through one centralized severity color source shared by all severity-displaying surfaces.

#### Scenario: Default preset preserves current severity colors
- **WHEN** no severity color preset has been stored
- **THEN** all severity-displaying surfaces SHALL render the same colors they render today.

#### Scenario: Preset changes apply to every severity-displaying surface
- **WHEN** the user selects a different severity color preset
- **THEN** Alerts, Events, and Incident views SHALL all reflect the new preset with no surface left showing the previous preset's colors.

### Requirement: Column Visibility For Supported Tables
The frontend SHALL allow the user to show or hide columns independently for each of the three supported tables (Alerts, Live Logs Event Feed, Incident views), and SHALL persist each table's configuration independently across sessions.

#### Scenario: Default shows all columns
- **WHEN** no column visibility preference has been stored for a supported table
- **THEN** that table SHALL render all of its existing columns exactly as it does today.

#### Scenario: Column visibility persists across sessions
- **WHEN** a user hides a column in a supported table and later reloads or revisits the table
- **THEN** that column SHALL remain hidden.

#### Scenario: Identifying column cannot be hidden
- **WHEN** a user configures column visibility for a supported table
- **THEN** that table's identifying column (`ID`) SHALL remain visible and SHALL NOT be configurable as hidden.

#### Scenario: One table's configuration does not affect another
- **WHEN** a user changes column visibility for one supported table
- **THEN** the column visibility of the other supported tables SHALL remain unchanged.

### Requirement: Live Log Highlighting Rules
The frontend SHALL allow the user to define highlighting rules that visually emphasize Live Logs rows matching a selected severity or event type, without altering stored or fetched event data.

#### Scenario: Default has no highlighting
- **WHEN** no highlighting rules have been stored
- **THEN** Live Logs SHALL render with no row highlighting, matching current behavior.

#### Scenario: Matching rows are visually emphasized
- **WHEN** a highlighting rule matches an event's severity or type
- **THEN** that event's row in the Live Logs Event Feed table SHALL render with the rule's visual treatment.

#### Scenario: Highlighting never changes underlying data
- **WHEN** one or more highlighting rules are active
- **THEN** the underlying event data, its fetch/filter/sort/search behavior, and any exported or copied representation of it SHALL remain unchanged; only the rendered row style SHALL differ.

#### Scenario: Highlighting applies consistently as events stream in
- **WHEN** new events arrive in Live Logs while highlighting rules are active
- **THEN** newly arriving matching events SHALL be highlighted using the same rules as already-displayed events, without requiring a manual refresh.

### Requirement: Display Preferences Are Frontend-Only
This spec SHALL be implemented without backend APIs, database changes, migrations, query-limit changes, or authentication changes.

#### Scenario: No backend contract is required
- **WHEN** this feature is implemented
- **THEN** no new backend endpoint, database table, migration, query-limit change, or auth/RBAC/audit-log behavior SHALL be required.

### Requirement: Alerts Over Time Honors Display Time Preferences
Alerts Over Time SHALL format axis and tooltip timestamps through the authoritative shared display formatter and SHALL NOT hard-code UTC labels.

#### Scenario: Local 12-hour chart display
- **WHEN** display settings select browser-local timezone and 12-hour timestamps
- **THEN** chart axis and tooltip labels SHALL use that timezone/format while retaining the correct underlying bucket instants and counts

#### Scenario: UTC 24-hour chart display
- **WHEN** display settings select UTC and 24-hour timestamps
- **THEN** chart axis and tooltip labels SHALL use UTC/24-hour output without a component-specific formatter

### Requirement: pfSense Ingest Filter Timestamps Honor Display Preferences
Human-facing timestamps in pfSense Ingest Filters SHALL use the authoritative shared display formatter without changing backend counter or policy semantics.

#### Scenario: Preference changes while panel is open
- **WHEN** the user changes timezone or timestamp-format preferences and opens or revisits pfSense Ingest Filters
- **THEN** policy and metrics timestamps SHALL reflect the selected settings and SHALL not remain forced to UTC/24-hour

### Requirement: Collapsed Sidebar Content Symmetry
The collapsed application shell SHALL provide symmetrical content gutters and SHALL remain responsive.

#### Scenario: Sidebar is collapsed
- **WHEN** the sidebar is collapsed at a supported desktop or narrow viewport
- **THEN** the main content SHALL have equal left/right outer gutters without chart clipping or horizontal overflow

### Requirement: Alert Detail Dark-Theme Contrast
Alert Details and its secondary content SHALL use explicit dark-theme foreground colors meeting WCAG 2.1 AA contrast requirements.

#### Scenario: Alert details render on dark background
- **WHEN** an alert detail panel, canonical outcome evidence, response state/log, manual action, lifecycle notice, or source-IP context is displayed
- **THEN** normal text SHALL meet at least 4.5:1 contrast and large text/non-text focus indicators SHALL meet at least 3:1 against their effective backgrounds

#### Scenario: Muted secondary text
- **WHEN** secondary information is visually muted
- **THEN** it SHALL remain readable at the applicable contrast threshold and SHALL not rely on an inherited near-black foreground

### Requirement: Fully Backward Compatible Defaults
Users who never open Settings SHALL see unchanged behavior for every preference defined by this spec, with the sole documented exception of consistent timestamp formatting replacing today's fragmented raw/forced-UTC rendering.

#### Scenario: Never-configured user sees preserved defaults
- **WHEN** a user has no `display` settings in localStorage
- **THEN** Live Logs font size, default tab, severity colors, table column visibility, rows-per-page/event limit, and Live Log highlighting SHALL all match today's existing behavior exactly.

#### Scenario: Corrupted display settings recover safely
- **WHEN** the stored `display` settings are malformed, partially invalid, or contain invalid values
- **THEN** the frontend SHALL recover invalid keys to their defaults individually, preserve valid keys, and SHALL NOT crash rendering of Alerts, Events, Live Logs, Incident views, or any supported table.
