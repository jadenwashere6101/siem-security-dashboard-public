## Overview

This parent roadmap is a coordination artifact only. It defines the full SIEM Settings feature suite, separates frontend-only preferences from backend-dependent preferences, records current risks/unknowns from the audit, and sequences child specs before any implementation begins.

## Current Audit Findings

- Navigation is centralized in `frontend/src/utils/sectionsConfig.js` and rendered by the grouped sidebar.
- The sidebar collapsed preference already uses localStorage through `frontend/src/utils/sidebarPreference.js`.
- Session identity currently uses sessionStorage and backend auth exposes username/role through `/auth/me`.
- There is no user preferences table or settings API in the current backend schema.
- Main dashboard alert refresh is hard-coded to 5 seconds in `frontend/src/App.js`.
- Live Logs has a separate hard-coded 5 second poller in `frontend/src/components/LiveLogsPanel.js`.
- Live Logs already supports Event Feed, Raw Log, and JSON view modes internally.
- Timestamp rendering is fragmented: some surfaces show raw backend strings, some force UTC, and some use browser locale defaults.
- `/events/search` hardcodes `LIMIT 100`; `/alerts` currently returns all alerts without a frontend-configurable limit.
- Severity color styling is duplicated across components.
- No browser Notification API or alert audio support was found in the current frontend.
- Existing component tests cover sidebar behavior, localStorage preference handling, Live Logs view behavior, Alerts, Incidents, and several settings-like service patterns.

## Storage Direction

v1 settings should use a frontend-only localStorage settings model with safe defaults and malformed-storage fallback behavior. This matches the existing sidebar preference pattern and avoids backend schema/API work for user preferences.

Backend DB/user-scoped settings are out of scope for v1 unless a future child spec explicitly adds them. A backend-backed expansion should be reserved for settings that must follow a user across browsers/devices or must be enforced by backend queries.

## Frontend-Only Settings

The following settings should be planned as frontend-only in v1 unless a child spec finds a concrete backend dependency:

- Settings sidebar/section visibility.
- localStorage settings model, defaults, and malformed localStorage handling.
- Default landing page among currently visible sections.
- Auto-refresh interval for frontend pollers, including Off.
- Timezone display where the frontend owns formatting.
- Timestamp format where the frontend owns formatting.
- Live Logs font size.
- Default Live Logs view.
- Severity color presets, after centralizing duplicated severity style logic.
- Column visibility on practical frontend-rendered tables.
- Live Log highlighting rules.
- Alert sound preference and browser notification preference as stored preferences and mocked tests only.

## Backend-Dependent Settings

The following should be tracked as backend-dependent or potentially backend-dependent:

- Rows per page / event limit when it must change `/events/search` beyond the current hard-coded `LIMIT 100`.
- Alert list limits or pagination if `/alerts` should stop returning all rows.
- User-scoped settings that persist across browsers/devices.
- Any settings API, settings table, migrations, or auth-linked preference writes.
- Real alert-trigger integration for browser notifications or audio if it depends on durable new-alert state beyond the current frontend polling model.

## Child Spec Plan

### siem-settings-foundation

Owns the first usable settings surface:

- Settings sidebar/section.
- localStorage settings model.
- Default values that preserve current behavior.
- Malformed localStorage handling.
- Default landing page.
- Auto-refresh interval.

### siem-display-preferences

Owns display and table/view behavior:

- Timezone display: Local browser time / UTC.
- Timestamp format: relative / absolute.
- Rows per page / event limit.
- Live Logs font size.
- Default Live Logs view: Event Feed / Raw Log / JSON.
- Severity color presets.
- Column visibility.
- Live Log highlighting rules.

### siem-alert-notification-preferences

Owns alert preference controls and browser API test strategy:

- Alert sound preference.
- Browser notification preference.
- Mocked `Notification` and audio tests.
- Future alert-trigger integration planning.

## Implementation Sequencing

1. Create and validate the parent roadmap.
2. Create `siem-settings-foundation`.
3. Implement foundation before display or notification preferences so later specs can reuse the settings store and defaults.
4. Create and implement `siem-display-preferences`.
5. Create and implement `siem-alert-notification-preferences`.
6. Defer backend/user-scoped expansion until after localStorage v1 behavior is validated.

## Validation Direction

Child specs should include focused frontend tests for defaults, malformed storage, navigation visibility, refresh intervals, timestamp formatting, Live Logs view/font/highlighting behavior, column visibility, and mocked browser notification/audio behavior.

If a child spec adds backend limits, APIs, migrations, or user preference persistence, it must include backend API/schema tests and deployment/runtime validation.

## Deployment / Rebuild Direction

This parent roadmap requires no VM sync. Future frontend-only implementation requires a frontend rebuild before deployment. Future backend changes require normal backend deployment, migration checks where applicable, service restart planning, and VM sync only after code is pushed and the VM working tree is confirmed clean.

## Risks And Unknowns

- Timestamp behavior is inconsistent today and may require a shared formatter before timezone/timestamp settings can be reliable.
- Main alerts and Live Logs use separate pollers, so auto-refresh settings must avoid partial or surprising behavior.
- Rows/event limits can be frontend-only for visible rows, but backend query limits need route changes.
- Column visibility can grow broad if it targets every table instead of a practical v1 subset.
- Severity presets require centralizing duplicated color logic.
- Real alert sounds/browser notifications need a clear definition of "new alert" to avoid repeated notifications on refresh.
- Browser notification permission prompts cannot be treated like ordinary toggles; users and browsers can deny or reset permission outside the app.
- Settings tied to role-gated sections must handle hidden/unavailable landing pages safely.
- localStorage is browser/device scoped and can be cleared or unavailable.
- Backend/user-scoped settings introduce schema, API, RBAC, migration, and audit considerations and should not be bundled into v1 by accident.
