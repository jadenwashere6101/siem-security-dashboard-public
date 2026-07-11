## Why

`siem-settings-roadmap` names `siem-display-preferences` as the second child implementation spec, to be built after `siem-settings-foundation` establishes the shared Settings section and localStorage-backed settings module. The roadmap's audit already found that timestamp rendering is fragmented (raw backend strings on some surfaces, a forced-UTC 24-hour helper on others, and independent local duplicates elsewhere), that severity badge color logic is duplicated with at least one real divergence between implementations, that Live Logs already has three view modes and hard-coded font sizes, and that no table currently supports column visibility or row-count control. This spec defines the display-customization surface that resolves those inconsistencies through user preferences, without adding any backend, database, or auth changes.

## What Changes

- Add a `display` section to the shared settings object introduced by `siem-settings-foundation`, covering: timezone mode, timestamp format, rows-per-page/event limit, Live Logs font size, default Live Logs tab, severity color preset, per-table column visibility, and Live Log highlighting rules.
- Define a single shared, settings-aware timestamp formatting helper that supersedes today's fragmented implementations (`utils/adminPanelDisplay.js#formatAdminTimestamp`'s forced-UTC/24-hour behavior, and the local `formatTimestamp` duplicates in `components/DeadLettersPanel.js` and `components/PlaybookExecutionTimeline.js`), and wires in the two SIEM surfaces that currently render a raw, unformatted `created_at` string with no helper at all (`components/AlertTableRow.js`, `components/LiveLogsPanel.js`).
- Define centralization of severity badge color logic so `components/IncidentsPanel.js`'s local `getSeverityBadgeStyle` (a 4-tier CRITICAL/HIGH/MEDIUM/LOW implementation) and `utils/threatHuntDisplay.js`'s shared `getSeverityBadgeStyle` (a 3-tier high/medium/low implementation, reused by `AlertsTable`, `DashboardSection`, `AlertGroupHeader`, and `ThreatHuntPanel`) converge on one severity-preset-aware source before presets can apply consistently.
- Define a frontend-only, client-side rows-per-page/event limit that caps how many already-fetched rows are rendered in `AlertsTable`, `LiveLogsPanel`'s Event Feed table, and `IncidentsPanel`'s table. This does not change the backend's hard-coded `LIMIT 100` in `/events/search` or the unlimited `/alerts` response; it only limits what is displayed from data the frontend already received.
- Define a practical v1 column-visibility subset for the three tables above (not every table in the app), each with a fixed, always-visible identifying column.
- Define Live Logs font size and default-tab preferences that apply to `components/LiveLogsPanel.js`'s existing `VIEW_MODES` and hard-coded inline `fontSize` values.
- Define Live Log highlighting rules as a purely presentational rule set (severity/event-type match to visual emphasis) that never mutates fetched event data.
- **MAC AI follow-up:** Route Alerts Over Time bucket labels and pfSense Ingest Filters metadata/counter timestamps through the existing shared display formatter so local/UTC and 12/24-hour preferences are authoritative on those surfaces.
- **MAC AI follow-up:** Make collapsed-sidebar content gutters symmetrical and perform a targeted dark-theme contrast correction for Alert Details and its secondary components, with measurable WCAG contrast gates.
- State explicitly that adopting the shared, settings-driven timestamp formatter is an intentional, spec-scoped visual normalization: today's raw-string surfaces and forced-UTC surfaces already disagree with each other, so no single default can be pixel-identical to all of them at once. The recommended default (local browser timezone, 24-hour) is chosen deliberately per user direction; selecting UTC reproduces the prior admin-panel convention. This normalization is what "timestamp formatting updates everywhere consistently" requires, and is treated as this spec's intended outcome rather than an unplanned regression. See `design.md`'s "Baseline Timestamp Behavior" section.
- Keep this implementation frontend-only; do not create a parallel settings/formatter system, touch the VM, commit, push, deploy, or mutate data during specification work.

## Capabilities

### New Capabilities
- `siem-display-preferences`: defines timezone, timestamp format, rows-per-page/event limit, Live Logs font size, default Live Logs tab, severity color presets, table column visibility, and Live Log highlighting-rule preferences, all localStorage-backed via the `siem-settings-foundation` settings module, with explicit default values, consuming components, and backward-compatibility behavior.

### Modified Capabilities
(none — this spec does not modify `siem-settings-foundation` or `siem-settings-roadmap`; it extends the settings schema those specs establish, which is additive)

## Impact

- **Owner:** MAC AI only.
- **Affected frontend (future implementation only):** existing consumers plus `TimelineChart.js`, `DashboardVisuals.js`, `PfsenseIngestFiltersPanel.js`, `SidebarLayout.js`, `AlertSidePanel.js`, Alert Details secondary components, shared display utilities, and focused tests/styles.
- **Affected backend:** none. No route, query limit, or API contract changes.
- **Affected database/migrations:** none.
- **Affected authentication/session behavior:** none.
- **Runtime behavior:** unchanged for any preference the user has not touched, except for the intentional, documented timestamp-rendering normalization described above.
- **Parent roadmap:** this child belongs to `siem-settings-roadmap` and depends on `siem-settings-foundation`'s settings module and Settings section existing first; no parent roadmap file changes are required for this spec.
- **Deployment:** future explicitly authorized frontend artifact deployment only; no backend restart, migration, or VM runtime verification is required.
