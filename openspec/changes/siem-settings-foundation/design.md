## Overview

`siem-settings-foundation` is the first child implementation spec under `siem-settings-roadmap`. It establishes a visible Settings surface and one shared frontend settings layer that later child specs can extend.

This scope is frontend-only. It must not introduce backend APIs, database tables, migrations, or auth/session changes.

## Existing Context

- Sidebar navigation is configured in `frontend/src/utils/sectionsConfig.js` and rendered by grouped sidebar components.
- Sidebar collapsed state already uses a small localStorage utility in `frontend/src/utils/sidebarPreference.js`.
- Auth/session identity uses the existing backend `/auth/me` flow and sessionStorage helper.
- Main alert refresh is currently hard-coded to 5 seconds in `frontend/src/App.js`.
- Live Logs has a separate hard-coded 5 second poller.
- The default active section is currently Dashboard.
- The UI is already dark mode and must remain dark mode only.

## Settings Architecture

Future implementation should introduce a dedicated frontend settings module, for example under `frontend/src/utils/` or `frontend/src/settings/`, that owns:

- A stable localStorage key.
- A versioned settings object.
- An exported defaults object.
- Read/parse/validate/merge helpers.
- Write helpers that only persist known supported keys.
- Recovery behavior for missing, invalid, partially invalid, or corrupted localStorage values.

The settings object should be extensible without breaking existing users. Unknown keys may be ignored on read/write, and missing keys should merge with defaults.

## Initial Settings Shape

The foundation settings should include only:

- `defaultLandingPage`
  - Default: `dashboard`.
  - Valid values: visible, known section ids that are safe to land on for the current user role.
- `autoRefreshIntervalMs`
  - Default: `5000`.
  - Valid values: `0`, `5000`, `10000`, `30000`, `60000`.
  - `0` means Off.

Future child specs may add display, Live Logs, table, color, and notification settings after this foundation exists.

## Settings Section

Future implementation should add a Settings section to the sidebar using the existing navigation/grouping pattern. The section should be visible to authenticated users and should not require super-admin permissions.

The Settings UI should expose controls for:

- Default landing page.
- Auto-refresh interval.

It should not expose a light/dark theme setting.

## Initialization Flow

On authenticated app load:

1. Read settings from localStorage.
2. If missing, use defaults.
3. If malformed or invalid, recover to defaults without crashing.
4. If partially valid, merge valid known values with defaults.
5. Select the active landing section from `defaultLandingPage` only if that section exists and is visible for the current role.
6. Fall back to Dashboard if the stored landing section is unavailable for the current role.
7. Apply `autoRefreshIntervalMs` to frontend polling behavior.

Logout should not be required to clear settings because v1 settings are browser preferences, not authenticated user records.

## Auto-Refresh Behavior

The current default behavior is a 5 second refresh. The default setting must preserve that value.

When Off is selected, automatic polling controlled by this foundation setting should stop, while manual refresh controls and initial load behavior remain available where they already exist.

Implementation should avoid introducing duplicate intervals or stale intervals when the setting changes.

## Dark Mode Boundary

The Settings foundation must preserve the current dark UI and must not introduce theme selection. Any future display preference work must also treat dark mode as permanent unless a later approved roadmap explicitly changes that boundary.

## Backend Boundary

v1 settings are localStorage-only. No backend APIs, settings tables, migrations, auth changes, RBAC changes, or audit-log changes are in scope for this child spec.

## Backward Compatibility

Existing users with no settings in localStorage should see the same default Dashboard landing page and 5 second auto-refresh behavior as before.

Invalid localStorage must not break login, navigation, refresh, or dashboard rendering.
