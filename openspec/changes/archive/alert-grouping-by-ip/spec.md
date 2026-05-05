# Alert Grouping by IP Spec

## Feature Overview

This change groups alerts by `source_ip` in the Alerts table.

The goal is to let analysts see attack chains from the same IP at a glance, instead of scanning a flat list of individual alerts.

## Current State

- Alerts are displayed as a flat list
- The investigation view shows related alerts only after an alert is selected
- No grouping exists in the main table
- Attack chains are not visually obvious from the main list alone

## Requirements

1. Grouping behavior
   - Group alerts by `source_ip`
   - Each group represents one IP
   - Alerts within each group should preserve the existing alert ordering behavior

2. Group header
   - Each group should have a header row showing:
     - `source_ip`
     - location, if available
     - total alert count
   - Optionally show the highest severity present in the group

3. Expand/collapse
   - Each group should be collapsible
   - Default state should be expanded for v1

4. Alert rows within group
   - Existing alert rows should render unchanged inside each group
   - Preserve:
     - badges
     - styling
     - click behavior that opens the Alert Details panel

5. Interaction
   - Clicking an alert must still open the right-side Alert Details panel
   - Grouping must not break:
     - filtering
     - searching
     - sorting

6. Filtering and search behavior
   - Filtering and search must still operate on individual alerts
   - Groups should update dynamically based on the already filtered alert list
   - If only one alert remains for an IP, grouping still applies

7. Scope
   - Frontend only
   - Likely modify:
     - `AlertsTable.js`
     - optionally `App.js` only if grouping logic is better centralized there
   - Do not modify backend, schema, or API

8. Visual design
   - Keep grouping visually subtle
   - Avoid heavy containers or card-like nesting
   - Prefer minimal indentation, divider rows, or lightweight section headers

9. Group ordering
   - Groups should follow the existing sort order based on their most recent alert
   - Example:
     - If sorting by `Newest`, the group with the newest alert appears first
   - Do not introduce a separate group sorting system

10. Table structure constraints
   - Do not break existing table column alignment
   - Group headers must span full width (`colspan`)
   - Alert rows must remain valid table rows (`<tr>`)
   - Do not convert the table into a `div`-based layout

11. Group header interaction
   - Clicking a group header should only expand or collapse the group
   - It must not open the Alert Details panel
   - Only actual alert rows trigger alert selection

## Non-Goals

- No cross-IP correlation view
- No case management system
- No persistence of collapsed state
- No drag-and-drop or advanced interactions
- No backend changes
- No API changes

## Acceptance Criteria

1. Alerts are grouped by `source_ip` in the table
2. Groups are clearly distinguishable
3. Clicking alerts still works as before
4. Filters, search, and sort still behave correctly
5. The UI remains clean and not cluttered
6. Frontend build succeeds

## Risks

- Visual clutter if grouping is too heavy
- Breaking table layout alignment
- Confusing interaction if group headers look too similar to real alert rows
- Performance issues if grouping is implemented inefficiently
