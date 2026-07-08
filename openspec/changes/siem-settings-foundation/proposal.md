## Why

The SIEM Settings roadmap identifies a need for a visible Settings section and a shared preference foundation before display-specific or notification-specific settings are added. This child spec creates that foundation while preserving the current dark UI and current behavior by default.

## What Changes

- Add the first implementation spec under the parent roadmap `openspec/changes/siem-settings-roadmap`.
- Add a visible Settings category/section in the sidebar.
- Define a frontend settings architecture with a localStorage-backed settings model.
- Define default settings values that preserve current behavior until a user changes a setting.
- Define graceful handling for missing, malformed, corrupted, or unavailable localStorage.
- Define the default landing page preference.
- Define the global auto-refresh interval preference.
- Define settings initialization flow and future extensibility for additional settings.
- Keep dark mode permanent and exclude any light/dark theme switch.
- Keep v1 frontend-only: no backend APIs, database tables, migrations, or authentication changes.

## Capabilities

### New Capabilities
- `siem-settings-foundation`: provides the Settings sidebar section, frontend settings model, localStorage persistence, default values, initialization behavior, default landing page preference, global auto-refresh preference, and extension points for future settings.

### Modified Capabilities
(none - this spec introduces a new settings foundation without changing existing backend requirements)

## Impact

- **Affected frontend:** future implementation will touch navigation/configuration, app initialization, refresh polling, and new settings UI/storage utilities.
- **Affected backend:** none.
- **Affected database/migrations:** none.
- **Affected authentication/session behavior:** none.
- **Runtime default behavior:** unchanged until the user changes a setting.
- **Parent roadmap:** this child belongs to `siem-settings-roadmap`; no parent file changes are required for this spec.
