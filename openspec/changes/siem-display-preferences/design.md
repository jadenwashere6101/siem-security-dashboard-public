## Overview

`siem-display-preferences` is the second child implementation spec under `siem-settings-roadmap`, built after `siem-settings-foundation`. It owns display and view-behavior preferences: timezone, timestamp format, rows-per-page/event limit, Live Logs font size, default Live Logs tab, severity color presets, table column visibility, and Live Log highlighting rules.

This scope is frontend-only. It must not introduce backend APIs, database tables, migrations, query-limit changes, or auth/session changes.

## Dependency On `siem-settings-foundation`

This spec assumes `siem-settings-foundation` has already defined:
- A single, versioned, localStorage-backed settings object with a stable key.
- Read/parse/validate/merge helpers that recover safely from missing, malformed, or partially valid stored data.
- Write helpers that persist only known supported keys.
- A visible Settings section in the sidebar.

`siem-display-preferences` extends that same settings object with a `display` section (see "Settings Shape" below) rather than introducing a second storage key or a parallel settings mechanism. If `siem-settings-foundation` has not yet been implemented when this spec's implementation begins, the display settings module may be built against the schema defined here and wired into the shared module once it exists, but it must not invent a separate long-term storage key.

## Existing Context (Audit)

- **Timestamp rendering is fragmented across at least four patterns today:**
  - `frontend/src/utils/adminPanelDisplay.js#formatAdminTimestamp` forces `timeZone: "UTC"`, `hour12: false`, and a fixed `"MMM DD, YYYY, HH:mm UTC"`-style format. Used by `components/IncidentsPanel.js` and `components/ApprovalsPanel.js` (`const formatTimestamp = (value) => formatAdminTimestamp(value, "N/A")`).
  - `components/DeadLettersPanel.js` and `components/PlaybookExecutionTimeline.js` each define their own local `formatTimestamp` function, independent of `adminPanelDisplay.js` and of each other.
  - `components/AlertTableRow.js` renders `{alert.created_at}` directly — the raw backend string, completely unformatted.
  - `components/LiveLogsPanel.js` renders `event.created_at || "N/A"` directly in its Event Feed table, and interpolates the same raw string into its Raw Log and JSON view text builders.
- **Severity badge color logic is duplicated with a real divergence:**
  - `frontend/src/utils/threatHuntDisplay.js#getSeverityBadgeStyle` is a 3-tier implementation (`high` / `medium` / `low`, default neutral). It is imported and reused by `components/AlertsTable.js`, `components/AlertTableRow.js`, `components/AlertGroupHeader.js`, `components/DashboardSection.js`, and `components/ThreatHuntPanel.js`.
  - `components/IncidentsPanel.js` defines its own local `getSeverityBadgeStyle` (line ~605), a 4-tier implementation (`CRITICAL` / `HIGH` / `MEDIUM` / `LOW`, default neutral) backed by its own local `criticalBadgeStyle`/`highBadgeStyle`/`mediumBadgeStyle`/`lowBadgeStyle`/`neutralBadgeStyle` constants, using upper-cased matching instead of `threatHuntDisplay.js`'s lower-cased matching.
  - These two implementations must converge on one shared, severity-preset-aware source before "severity color presets" (plural, i.e. selectable palettes) can behave consistently across Alerts, Incidents, and Threat Hunt/Events surfaces. Converging them also means deciding whether the SIEM-wide severity vocabulary includes `critical` as a fourth tier (Incidents already relies on it) — this decision must be made explicitly during implementation and applied identically everywhere, not left as a per-surface difference.
- **No table currently supports column visibility or a frontend row/event limit.** The practical v1 subset of tables (all render every column of every fetched row, unbounded):
  - `components/AlertsTable.js` (via `components/AlertsTableHeader.js`): `ID`, `Type`, `Source`, `Source IP`, `Behavior`, `Severity`, `Message`, `Created At`, `Action` (9 columns).
  - `components/LiveLogsPanel.js` Event Feed table: `ID`, `Type`, `Severity`, `Source IP`, `App`, `Message`, `Created` (7 columns).
  - `components/IncidentsPanel.js` table: `ID`, `Title`, `Severity`, `Priority`, `Status`, `Source IP`, `Created` (7 columns).
- **Live Logs already has the view-mode and font infrastructure this spec builds on:**
  - `components/LiveLogsPanel.js` defines `VIEW_MODES` (`eventFeed`, `rawLog`, `json`) and a `viewMode` state initialized unconditionally to `VIEW_MODES.eventFeed` via `useState`.
  - Font sizes are hard-coded inline per style object (`10px`–`13px` across roughly a dozen style constants in the file) with no shared scale.
- **Row/event limits today:** `/events/search` hard-codes `LIMIT 100` server-side; `/alerts` returns all rows with no limit. Neither `AlertsTable`, `LiveLogsPanel`, nor `IncidentsPanel` performs any client-side slicing today — every fetched row is rendered. This means the only behavior-preserving default for a new "rows per page / event limit" setting is "show everything already fetched" (see "Rows Per Page / Event Limit" below); any smaller default would visibly truncate what users see today.
- The UI is dark mode only and must remain so; no color preset introduces a light theme.

## Settings Shape

Extends the shared settings object with a `display` section:

```
display: {
  timezoneMode: "local" | "utc",              // default: "local"
  timestampFormat: "12h" | "24h",              // default: "24h"
  rowsPerPage: "all" | 25 | 50 | 100 | 250,     // default: "all"
  liveLogsFontSize: "small" | "medium" | "large", // default: "medium"
  defaultLiveLogsTab: "eventFeed" | "rawLog" | "json", // default: "eventFeed"
  severityColorPreset: "default" | "colorblindSafe" | "highContrast", // default: "default"
  columnVisibility: {
    alertsTable: { <columnKey>: boolean, ... },     // default: all true
    liveLogsTable: { <columnKey>: boolean, ... },   // default: all true
    incidentsTable: { <columnKey>: boolean, ... },  // default: all true
  },
  liveLogHighlightRules: [
    { id: string, matchType: "severity" | "eventType", matchValue: string, style: "border" | "background" | "glow", color: string }
  ], // default: []
}
```

Unknown keys within `display` are ignored on read (per the foundation's extensibility contract); missing keys merge with the defaults above. `columnVisibility` and `liveLogHighlightRules` are themselves recoverable per-entry: one invalid column key or one invalid highlight rule must not discard the rest of the valid settings.

## Timezone And Timestamp Format

- `timezoneMode` controls whether displayed timestamps use the browser's local timezone (`Intl` default/`undefined` `timeZone`) or a fixed `UTC` timezone.
- `timestampFormat` controls `hour12: true` (12-hour) vs `hour12: false` (24-hour) in the shared formatter's `Intl.DateTimeFormat` options.
- A single shared, settings-aware timestamp formatting helper (extending or replacing `utils/adminPanelDisplay.js#formatAdminTimestamp`) becomes the one place that reads `timezoneMode`/`timestampFormat` and formats a timestamp. All consumers listed under "Consuming Components" call this helper instead of formatting timestamps themselves or leaving them raw.
- Invalid or unparseable timestamp values must render a safe fallback (matching today's existing fallback behavior per surface, e.g. `"N/A"` or the raw value) rather than `"Invalid Date"` or a thrown error.

### Baseline Timestamp Behavior (Design Decision)

Today's timestamp rendering already disagrees with itself: `IncidentsPanel`/`ApprovalsPanel` force UTC/24-hour through `formatAdminTimestamp`; `AlertTableRow`/`LiveLogsPanel` show the raw, unformatted backend string; `DeadLettersPanel`/`PlaybookExecutionTimeline` each apply their own independent formatting. There is no single existing "default" that a new shared formatter could reproduce identically on every surface at once — unifying them is this spec's explicit purpose ("timestamp formatting updates everywhere consistently").

Given that, the following is the deliberate default and is not an oversight:
- The recommended and technical default is `timezoneMode: "local"`, `timestampFormat: "24h"`, per this spec's explicit product direction.
- Selecting `timezoneMode: "utc"` with `timestampFormat: "24h"` reproduces the exact timezone/format convention `IncidentsPanel` and `ApprovalsPanel` already use today, for users who want continuity with that specific prior look.
- Surfaces that previously showed a raw, unformatted string (`AlertTableRow`, `LiveLogsPanel`) will show a formatted, human-readable timestamp for the first time under any setting value, including the default. This is treated as a correctness improvement (a raw ISO-ish string is not "no timestamp," it is an unstyled one) and an explicit, intended part of this spec's consistency goal, not a silent behavior change to be hidden.
- "Defaults preserved for users who never open Settings" (see acceptance criteria) means: no crash, no data loss, no loss of functionality, and every currently-displayed timestamp continues to display a value derived from the same underlying `created_at`/`timestamp` field — not that every surface's rendered string is byte-identical to today's fragmented output. This distinction must be confirmed with whoever accepts this spec before implementation begins (see `tasks.md` Phase 0).

## Rows Per Page / Event Limit

- `rowsPerPage` is a purely frontend, client-side cap on how many already-fetched rows are rendered in a table. It does not change `/events/search`'s server-side `LIMIT 100` or add a limit to `/alerts`. No request parameter, query string, or API contract changes.
- Default is `"all"` (no cap), because none of `AlertsTable`, `LiveLogsPanel`, or `IncidentsPanel` currently slices its rendered rows — every fetched row is shown today. Any smaller default would visibly truncate what current users already see, violating "defaults preserved."
- When set to a numeric value (`25`/`50`/`100`/`250`), the table renders only the first N rows of its already-fetched, already-filtered/sorted data (i.e., applied after existing search/filter/sort logic, not instead of it).
- This setting is distinct from, and must not be confused with, a future backend-supported pagination or query-limit change; that remains explicitly out of scope per the parent roadmap's backend-dependent settings list.

## Live Logs Font Size

- `liveLogsFontSize` maps to a small scale (e.g. `small` ≈ current sizes − 1–2px, `medium` = today's existing hard-coded sizes unchanged, `large` ≈ current sizes + 1–2px) applied uniformly across `LiveLogsPanel.js`'s per-element font sizes, preserving each element's relative size difference rather than forcing one uniform size.
- Default is `medium`, defined as exactly today's existing hard-coded values, so a user who never opens Settings sees identical Live Logs text size.
- The change must apply immediately (no reload required) when the setting changes while Live Logs is open.

## Default Live Logs Tab

- `defaultLiveLogsTab` controls the initial value of `LiveLogsPanel.js`'s `viewMode` state (`VIEW_MODES.eventFeed` / `VIEW_MODES.rawLog` / `VIEW_MODES.json`) when the panel mounts, replacing the current unconditional default of `VIEW_MODES.eventFeed`.
- Default is `eventFeed`, matching today's unconditional initial value exactly.
- Manually clicking the Event Feed/Raw Log/JSON toggle during a session continues to work exactly as it does today; this setting only affects the tab selected on mount, and persists the user's most recently selected default across sessions (updated when the user explicitly changes their preferred default in Settings, not silently on every click — see `tasks.md` for the exact persistence trigger to confirm during implementation).

## Severity Color Presets

- Requires centralizing `threatHuntDisplay.js#getSeverityBadgeStyle` and `IncidentsPanel.js`'s local `getSeverityBadgeStyle` into one shared, preset-aware function before presets can apply consistently (see "Existing Context" above for the exact divergence). This centralization is in scope for this spec because color presets cannot be implemented correctly on top of two disagreeing implementations.
- `severityColorPreset` selects among named palettes (`default`, `colorblindSafe`, `highContrast`) that each map the same severity vocabulary to a distinct set of colors; the `default` preset must reproduce today's existing colors exactly (post-centralization) so a user who never opens Settings sees no visual change.
- The centralized helper must resolve, and apply identically everywhere, whether `critical` is a first-class severity tier (as `IncidentsPanel` treats it today) or continues to be folded into `high` (as `threatHuntDisplay.js` treats it today); this decision is made once, in the shared helper, not per-surface.

## Column Visibility For Tables

- Scoped to the practical v1 subset identified in "Existing Context": `AlertsTable`, `LiveLogsPanel`'s Event Feed table, and `IncidentsPanel`'s table. No other table is in scope for this spec.
- Each table's `columnVisibility` entry lists its own column keys with independent booleans; hiding a column removes both its header cell and its body cells for that table only.
- Each table retains one non-hideable identifying column (`ID` for all three) so a table can never be configured into an unusable, unidentifiable state.
- Default is all columns visible for all three tables, matching today's behavior exactly.

## Live Log Highlighting Rules

- A `liveLogHighlightRules` list of presentation-only rules, each matching on `severity` or event `type` (`matchType`/`matchValue`) and applying a visual treatment (`style`: left border, background tint, or glow; `color`) to matching rows in `LiveLogsPanel.js`'s Event Feed table only.
- Rules affect only the rendered style of a row; they must never mutate the underlying event object, filter/hide rows, or change what is fetched, sorted, searched, or exported.
- Default is an empty rule list, matching today's unhighlighted appearance exactly.
- Rules apply consistently as new events stream in without requiring a manual refresh or re-render trigger beyond the panel's existing update cycle.

## Consuming Components

| Setting | Primary consumers |
| --- | --- |
| `timezoneMode` / `timestampFormat` | Shared timestamp helper (extends/replaces `utils/adminPanelDisplay.js`); `components/AlertTableRow.js` (Alerts); `components/LiveLogsPanel.js` (Live Logs); `components/IncidentsPanel.js` (Incident views); `components/DeadLettersPanel.js`, `components/PlaybookExecutionTimeline.js`, `components/ApprovalsPanel.js` (existing timestamp-helper consumers migrated for consistency) |
| `rowsPerPage` | `components/AlertsTable.js` (Alerts/Tables); `components/LiveLogsPanel.js` (Live Logs); `components/IncidentsPanel.js` (Incident views/Tables) |
| `liveLogsFontSize` | `components/LiveLogsPanel.js` (Live Logs) |
| `defaultLiveLogsTab` | `components/LiveLogsPanel.js` (Live Logs) |
| `severityColorPreset` | Shared severity helper (centralizing `utils/threatHuntDisplay.js` and `components/IncidentsPanel.js`); `components/AlertsTable.js`, `components/AlertTableRow.js`, `components/AlertGroupHeader.js`, `components/DashboardSection.js` (Alerts/Tables); `components/ThreatHuntPanel.js` (Events); `components/IncidentsPanel.js` (Incident views) |
| `columnVisibility` | `components/AlertsTable.js` + `components/AlertsTableHeader.js` (Alerts/Tables); `components/LiveLogsPanel.js` (Live Logs/Tables); `components/IncidentsPanel.js` (Incident views/Tables) |
| `liveLogHighlightRules` | `components/LiveLogsPanel.js` (Live Logs only) |

## Dark Mode Boundary

This spec must not introduce a light theme, a theme switch, or any color preset that departs from the dark UI shell. Severity color presets change badge/highlight accent colors only, within the existing dark background.

## Backend Boundary

v1 display settings are localStorage-only, extending the same shared settings object as `siem-settings-foundation`. No backend endpoint, database table, migration, query-limit change, RBAC change, or audit-log change is in scope for this child spec.

## Backward Compatibility

A user with no `display` settings in localStorage (or with `siem-settings-foundation`'s settings object present but no `display` key yet) must see: identical Live Logs font size and default tab, identical severity colors, all table columns visible, no row truncation, and no Live Log highlighting — with the one intentional exception documented above under "Baseline Timestamp Behavior," where previously raw/unformatted or forced-UTC timestamps become consistently formatted per the default timezone/format setting.

Invalid, partial, or corrupted `display` settings must recover to defaults per-key (not discard the entire settings object) and must never crash rendering of Alerts, Events, Live Logs, Incident views, or any table.
