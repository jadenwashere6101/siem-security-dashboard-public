## 1. MAC AI — Scope Confirmation

- [ ] 1.1 Confirm this child spec belongs under the parent roadmap `openspec/changes/siem-settings-roadmap` and depends on `siem-settings-foundation`'s settings module and Settings section.
- [ ] 1.2 Confirm implementation scope is frontend-only.
- [ ] 1.3 Confirm no backend APIs, database tables, migrations, or query-limit changes are added.
- [ ] 1.4 Confirm no authentication/session changes are added.
- [ ] 1.5 Confirm no light/dark theme setting is added; severity color presets only change accent colors within the existing dark UI.
- [ ] 1.6 Confirm the "Baseline Timestamp Behavior" design decision in `design.md` (recommended default is local timezone/24-hour; this normalizes today's fragmented raw/forced-UTC timestamp rendering) with whoever accepts this spec before implementation begins.
- [ ] 1.7 Confirm all other defaults (Live Logs font size, default tab, severity colors, column visibility, rows-per-page, highlighting) preserve exactly today's existing behavior.

## 2. MAC AI — Display Settings Schema

- [ ] 2.1 Extend the shared settings module's schema (from `siem-settings-foundation`) with a `display` section matching `design.md`'s "Settings Shape".
- [ ] 2.2 Define defaults: `timezoneMode: "local"`, `timestampFormat: "24h"`, `rowsPerPage: "all"`, `liveLogsFontSize: "medium"`, `defaultLiveLogsTab: "eventFeed"`, `severityColorPreset: "default"`, `columnVisibility` all-true for `alertsTable`/`liveLogsTable`/`incidentsTable`, `liveLogHighlightRules: []`.
- [ ] 2.3 Add validation for each `display` key against its allowed values; invalid values fall back to that key's default without discarding other valid `display` keys.
- [ ] 2.4 Add per-entry recovery for `columnVisibility` (invalid table/column key ignored, not the whole map) and `liveLogHighlightRules` (invalid rule entry dropped, not the whole list).
- [ ] 2.5 Ensure `display` settings round-trip through the same read/write helpers as `siem-settings-foundation`'s existing settings, without introducing a second storage key.

## 3. MAC AI — Shared Timestamp Helper

- [ ] 3.1 Create or extend one shared, settings-aware timestamp formatting helper (e.g. extending `frontend/src/utils/adminPanelDisplay.js#formatAdminTimestamp` or a new dedicated module) that reads `timezoneMode`/`timestampFormat` from the display settings and returns a formatted string with a safe fallback for invalid/missing values.
- [ ] 3.2 Update `components/IncidentsPanel.js` and `components/ApprovalsPanel.js` to call the shared helper instead of the current forced-UTC `formatAdminTimestamp` usage.
- [ ] 3.3 Update `components/DeadLettersPanel.js` and `components/PlaybookExecutionTimeline.js` to call the shared helper instead of their local `formatTimestamp` implementations.
- [ ] 3.4 Update `components/AlertTableRow.js` to render `alert.created_at` through the shared helper instead of the raw string.
- [ ] 3.5 Update `components/LiveLogsPanel.js`'s Event Feed table `created_at` cell to use the shared helper instead of the raw string; leave the Raw Log/JSON tabs' literal payload text unchanged, since those views intentionally show source-preserved raw text (per existing Live Logs behavior).
- [ ] 3.6 Confirm no other timestamp-formatting call site was missed via a repo-wide search for `formatTimestamp`/`toLocaleString`/`toISOString`/raw `created_at` rendering.
- [x] 3.7 Refactor Alerts Over Time data to retain numeric bucket instants and format axis/tooltip labels through the shared helper using current display settings.
- [x] 3.8 Pass authoritative display settings into pfSense Ingest Filters and replace forced-UTC policy/metrics timestamp rendering with the shared helper.
- [x] 3.9 Test chart bucket/count preservation, local/UTC labels, 12/24-hour labels, tooltip output, pfSense timestamps, invalid values, and live preference changes.

## 4. MAC AI — Rows Per Page / Event Limit

- [ ] 4.1 Add a client-side row-limiting step (applied after existing filter/sort logic) to `components/AlertsTable.js`, `components/LiveLogsPanel.js`'s Event Feed table, and `components/IncidentsPanel.js`'s table, driven by `display.rowsPerPage`.
- [ ] 4.2 Confirm `"all"` renders every already-fetched row with no truncation, matching current behavior exactly.
- [ ] 4.3 Confirm no request parameter, query string, or API call changes as a result of this setting.
- [ ] 4.4 Confirm this setting is documented as distinct from any future backend-supported pagination/query-limit change (out of scope here).

## 5. MAC AI — Live Logs Font Size

- [ ] 5.1 Define a small font-size scale (`small`/`medium`/`large`) for `components/LiveLogsPanel.js`, with `medium` set to exactly today's existing hard-coded per-element sizes.
- [ ] 5.2 Wire `display.liveLogsFontSize` into the panel's style constants so all sizes shift together, preserving each element's relative size difference.
- [ ] 5.3 Confirm the change applies immediately while Live Logs is open, with no reload required.

## 6. MAC AI — Default Live Logs Tab

- [ ] 6.1 Initialize `components/LiveLogsPanel.js`'s `viewMode` state from `display.defaultLiveLogsTab` instead of the current unconditional `VIEW_MODES.eventFeed`.
- [ ] 6.2 Confirm the default (`eventFeed`) matches today's unconditional initial value exactly.
- [ ] 6.3 Confirm manual tab switching during a session continues to work exactly as today, independent of the stored default.
- [ ] 6.4 Confirm the setting persists across sessions and define, precisely, when the stored default updates (e.g., only via an explicit Settings control, not implicitly on every manual tab click) before implementation.

## 7. MAC AI — Severity Color Presets

- [ ] 7.1 Centralize `utils/threatHuntDisplay.js#getSeverityBadgeStyle` and `components/IncidentsPanel.js`'s local `getSeverityBadgeStyle` into one shared, preset-aware severity color function.
- [ ] 7.2 Resolve the 3-tier (high/medium/low) vs. 4-tier (critical/high/medium/low) divergence explicitly, applying the resolved vocabulary identically on every consuming surface.
- [ ] 7.3 Update `components/AlertsTable.js`, `components/AlertTableRow.js`, `components/AlertGroupHeader.js`, `components/DashboardSection.js`, `components/ThreatHuntPanel.js`, and `components/IncidentsPanel.js` to consume the centralized function.
- [ ] 7.4 Define the `default`, `colorblindSafe`, and `highContrast` presets; confirm `default` reproduces today's existing colors exactly (post-centralization).
- [ ] 7.5 Wire `display.severityColorPreset` into the centralized function so changing the preset updates every consuming surface with no surface left on the previous preset.

## 8. MAC AI — Column Visibility For Supported Tables

- [ ] 8.1 Add a column-visibility mechanism to `components/AlertsTable.js`/`components/AlertsTableHeader.js` covering its 9 existing columns (`ID`, `Type`, `Source`, `Source IP`, `Behavior`, `Severity`, `Message`, `Created At`, `Action`), keyed by `display.columnVisibility.alertsTable`.
- [ ] 8.2 Add the same mechanism to `components/LiveLogsPanel.js`'s Event Feed table covering its 7 existing columns (`ID`, `Type`, `Severity`, `Source IP`, `App`, `Message`, `Created`), keyed by `display.columnVisibility.liveLogsTable`.
- [ ] 8.3 Add the same mechanism to `components/IncidentsPanel.js`'s table covering its 7 existing columns (`ID`, `Title`, `Severity`, `Priority`, `Status`, `Source IP`, `Created`), keyed by `display.columnVisibility.incidentsTable`.
- [ ] 8.4 Keep each table's `ID` column always visible and non-configurable as hidden.
- [ ] 8.5 Confirm each table's configuration persists and is scoped independently (hiding a column in one table does not affect another).
- [ ] 8.6 Confirm default (all columns visible) matches today's behavior exactly.

## 9. MAC AI — Live Log Highlighting Rules

- [ ] 9.1 Add a `liveLogHighlightRules`-driven row-style layer to `components/LiveLogsPanel.js`'s Event Feed table only, matching on `severity` or event `type`.
- [ ] 9.2 Implement the three visual treatments (`border`, `background`, `glow`) as pure style application; confirm no rule ever mutates `event` data, filtering, sorting, or search behavior.
- [ ] 9.3 Confirm newly streamed-in events are evaluated against active rules the same way as already-displayed events, without requiring a manual refresh.
- [ ] 9.4 Confirm the default (no rules) matches today's unhighlighted appearance exactly.

## 10. MAC AI — Shell Symmetry and Alert Contrast Pass

- [x] 10.1 Make collapsed `SidebarLayout` main-content gutters equal while preserving intentional expanded-sidebar separation.
- [x] 10.2 Audit effective colors in Alert Details, ResponseOutcome, response state/log, manual actions, lifecycle notice, and source-IP context; replace accidental inheritance with explicit dark-theme tokens.
- [x] 10.3 Measure normal text at 4.5:1 minimum and large text/focus/non-text UI at 3:1 minimum against effective backgrounds.
- [x] 10.4 Add component/layout tests for collapsed/expanded gutters and explicit readable alert-detail foregrounds.
- [x] 10.5 Verify desktop, 1280px, tablet, and narrow/mobile layouts, chart resizing, keyboard focus, and horizontal overflow with visual evidence when practical.

## 11. MAC AI — Tests To Add During Implementation

- [ ] 11.1 Unit test the shared timestamp helper: default (local/24h), UTC selection, 12-hour selection, invalid/missing value fallback.
- [ ] 11.2 Unit test the centralized severity color function: default preset matches prior colors on both the 3-tier and 4-tier call sites; preset switching; resolved critical/high vocabulary.
- [ ] 11.3 Unit/component test `rowsPerPage` on each of the three tables: `"all"` shows every row; a numeric value truncates only rendered rows, applied after filter/sort.
- [ ] 11.4 Component test Live Logs font size scale and immediate application.
- [ ] 11.5 Component test default Live Logs tab initialization and persistence across a simulated reload, plus unaffected manual switching.
- [ ] 11.6 Component test column visibility per table: default all-visible, independent persistence per table, non-hideable `ID` column.
- [ ] 11.7 Component test Live Log highlighting: no rules by default; matching rule applies visual treatment; non-mutation of underlying event data; newly streamed events are evaluated against active rules.
- [ ] 11.8 Regression test that `display` settings recover safely from malformed/partial localStorage without crashing Alerts, Events, Live Logs, or Incident views.
- [ ] 11.9 Regression test that no `/events/search`, `/alerts`, or other API request changes shape/parameters as a result of any setting in this spec.

## 12. MAC AI — Validation To Run During Implementation

- [x] 12.1 Run focused frontend tests for the shared timestamp helper and its consumers.
- [ ] 12.2 Run focused frontend tests for the centralized severity color function and its consumers.
- [x] 12.3 Run focused frontend tests for rows-per-page, column visibility, Live Logs font size/default tab, highlighting, chart/pfSense timestamps, shell spacing, and Alert Details contrast.
- [x] 12.4 Run existing Alerts, Live Logs, Incidents, pfSense, SidebarLayout, and dashboard chart suites to confirm no regression.
- [x] 12.5 Run `npm test -- --watchAll=false` from `frontend/` if practical for the implementation change.
- [x] 12.6 Run `npm run build`, `openspec validate siem-display-preferences --strict`, and `git diff --check`.

## 13. MAC AI — Out Of Scope and Stop Conditions

- [ ] 13.1 Do not add backend settings APIs, query-limit changes, or pagination endpoints.
- [ ] 13.2 Do not add database persistence or migrations.
- [ ] 13.3 Do not change authentication, sessions, or RBAC.
- [ ] 13.4 Do not add theme switching or a light theme.
- [ ] 13.5 Do not add column visibility to tables outside the three named in this spec.
- [ ] 13.6 Do not implement alert sound or browser notification preferences from `siem-alert-notification-preferences`.
- [ ] 13.7 Do not modify `siem-settings-foundation` or `siem-settings-roadmap` beyond reading their established schema/contract.
- [ ] 13.8 Do not touch the VM.
- [ ] 13.9 Stop if implementation changes backend timestamp/bucket data, requires a second settings/formatter source, introduces a light theme, or cannot meet the contrast gates.
- [ ] 13.10 Do not commit, push, deploy, or perform VM work without explicit authorization.
