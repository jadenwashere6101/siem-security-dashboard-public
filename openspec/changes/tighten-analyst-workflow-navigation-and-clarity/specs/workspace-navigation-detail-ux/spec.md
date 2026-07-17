## ADDED Requirements

### Requirement: Deep links into Recent Alerts SHALL use exact investigation targets
The frontend SHALL distinguish analyst investigation pivots from manual broad search when opening `Recent Alerts` from related workspaces.

#### Scenario: Related source-IP pivot
- **WHEN** a user opens related alerts from Recon Activity, incidents, Source-IP Context, or another analyst workflow that is explicitly targeting one source IP
- **THEN** Dashboard SHALL request `Recent Alerts` with an exact source-IP investigation filter rather than only the broad free-text search term, and SHALL still focus and scroll to the `Recent Alerts` destination

#### Scenario: Primary target pivot
- **WHEN** a user opens alerts for a specific target from a supported analyst workflow
- **THEN** Dashboard SHALL request `Recent Alerts` with an exact target filter rather than relying on a broad free-text match

### Requirement: Deep-link filter changes SHALL reset pagination before requesting rows
Dashboard deep links and filter changes SHALL apply their next list state atomically so the alert request is not sent once with stale pagination.

#### Scenario: Filter changes on a later page
- **WHEN** the user changes an alert filter or arrives through a deep link while `Recent Alerts` is on page 2 or later
- **THEN** the frontend SHALL reset pagination to the first page before requesting rows for the new filter state

#### Scenario: Background refresh after a deep link
- **WHEN** the dashboard quietly refreshes after an exact investigation deep link has been applied
- **THEN** the same exact filter state SHALL persist and the refresh SHALL NOT broaden the result set to unrelated alerts
