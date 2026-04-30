# AlertsTable Decomposition Plan

This document is a planning guide for future `AlertsTable.js` cleanup.

It is not an instruction to refactor now. The goal is to define safe future component boundaries before any code movement.

## 1. Current Responsibilities Inside `AlertsTable.js`

`AlertsTable.js` currently owns:

- table header controls for search, sort, severity/source/status filters
- filtered export links and export UI
- grouped alert-table rendering by `source_ip`
- badge/display helpers for source, severity, reputation, and correlation state
- local toast feedback
- response-log loading
- note loading and note submission
- response-action execution
- selected alert state and side-panel details
- selected alert timeline rendering
- large inline style clusters

## 2. Suggested Future Child Components

These are future candidates, not immediate extractions.

### A. `AlertsToolbar`

Would own:
- search input
- sort selector
- severity/source/status filters
- export trigger and export links
- “recent alerts” summary text

Likely props:
- `filteredAlerts.length`
- `resolvedAlerts.length`
- `searchTerm`, `setSearchTerm`
- `sortOption`, `setSortOption`
- `severityFilter`, `setSeverityFilter`
- `sourceFilter`, `setSourceFilter`
- `statusFilter`, `setStatusFilter`
- `multiAlertReportHref`
- `multiAlertCsvExportHref`
- `multiAlertPdfReportHref`
- `downloadPdfReport`
- style props already used by the header/filter area

Extraction risk:
- Low to medium

### B. `GroupedAlertsTable`

Would own:
- grouped alert table shell
- group header row
- collapsed/expanded group behavior
- mapping over grouped alerts

Likely props:
- `groupedFilteredAlerts`
- `collapsedGroups`
- `toggleGroup`
- `selectedAlertId`
- `setSelectedAlertId`
- `selectedAlert`
- `setSelectedAlert`
- `hoveredAlertId`
- `setHoveredAlertId`
- display helper functions used by rows
- shared table styles
- callbacks needed by row actions

Extraction risk:
- Medium

### C. `AlertTableRow`

Would own:
- a single rendered alert row
- row click behavior
- severity/source/correlation badges inside the row
- row action button wiring already passed down from parent

Likely props:
- `alert`
- `isSelected`
- `isHovered`
- `onHoverStart`
- `onHoverEnd`
- `onSelect`
- `onResolve`
- `onFetchResponseLog`
- `onFetchNotes`
- `onAddNote`
- `onExecuteAction`
- `canTakeAlertActions`
- badge/display helpers
- row/cell style props

Extraction risk:
- Medium to high

### D. `AlertDetailsPanel`

Would own:
- selected alert side panel
- selected alert metadata display
- source/reputation/correlation/MITRE sections
- report/export links for a selected alert

Likely props:
- `selectedAlert`
- `selectedAlertTimeline`
- `responseLogs[selectedAlert.id]`
- `alertNotes[selectedAlert.id]`
- `noteDrafts[selectedAlert.id]`
- loading/action state for the selected alert
- note/action handlers
- display helper functions
- expanded/detail style props

Extraction risk:
- Medium

### E. `AlertTimeline`

Would own:
- timeline list for the currently selected alert group
- per-item ordering/rendering

Likely props:
- `selectedAlertTimeline`
- `getSeverityBadgeStyle`
- minimal timeline-specific styles or reused detail styles

Extraction risk:
- Low

### F. `AlertNotesAndActions`

Would own:
- notes list
- note draft textarea/input
- add-note action
- response-action buttons
- response log display for selected alert

Likely props:
- `selectedAlert`
- `alertNotes`
- `noteDrafts`
- `responseLogs`
- `loadingNotesForAlertId`
- `addingNoteForAlertId`
- `executingActionId`
- `canTakeAlertActions`
- note/action handlers
- permission/error display helpers
- detail style props

Extraction risk:
- Medium to high

## 3. What Each Child Component Should Own

Ownership rule:
- keep data-fetching and mutation handlers in the parent at first
- extract presentation-heavy regions before behavior-heavy regions
- avoid changing prop names or moving API calls during the first extraction phase

Best early ownership split:
- `AlertsToolbar`: filter/export controls only
- `AlertTimeline`: selected-alert timeline only
- `AlertDetailsPanel`: read-heavy selected-alert UI before notes/actions are split

## 4. Risk Level For Extracting Each Component

- `AlertsToolbar`: Low to medium
- `AlertTimeline`: Low
- `AlertDetailsPanel`: Medium
- `GroupedAlertsTable`: Medium
- `AlertTableRow`: Medium to high
- `AlertNotesAndActions`: Medium to high

## 5. Recommended Extraction Order

Prefer the smallest safe extraction first.

1. `AlertTimeline`
2. `AlertsToolbar`
3. `AlertDetailsPanel`
4. `GroupedAlertsTable`
5. `AlertTableRow`
6. `AlertNotesAndActions`

Why this order:
- timeline is the narrowest UI-only region
- toolbar is mostly controlled inputs plus export links
- details panel is readable to separate once smaller display pieces are proven safe
- grouped table and row extraction are more coupled to selection/hover/group behavior
- notes/actions are the most stateful and mutation-heavy part of the component

## 6. What Should NOT Be Extracted Yet

Do not extract yet:
- API request handlers
- note/action mutation logic
- grouped row selection logic
- `selectedAlert` ownership
- `collapsedGroups` ownership
- large shared style sets if moving them would create noisy prop churn

Do not do:
- a one-shot split into many components
- prop renaming during the first extraction
- style-system cleanup at the same time as component extraction

## 7. Required Checks After Future Extraction

Run:

```bash
cd frontend && npm run build
```

Then visually verify:
- alerts table still renders correctly
- grouping by `source_ip` still works
- group collapse/expand still works
- selected row and expanded details still work
- export links/buttons still work
- notes still load and submit
- response actions still run
- selected-alert timeline still renders correctly

## 8. Practical Guidance

- Start with one child component only.
- Keep the parent in control of data and handlers at first.
- If the first extraction introduces lots of prop churn, stop and re-scope smaller.
- The goal is lower editing risk, not a “perfect” component tree in one pass.
